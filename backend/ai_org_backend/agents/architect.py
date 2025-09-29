"""Architect agent utilities and Celery tasks."""

from __future__ import annotations

import logging
import time
from typing import Any

from celery import shared_task
from sqlmodel import Session, select

from ai_org_backend.agents.utils import load_template
from ai_org_backend.db import SessionLocal
from ai_org_backend.main import Repo
from ai_org_backend.metrics import prom_counter, prom_hist
from ai_org_backend.models import Purpose, Task, TaskDependency, TaskOwner, TaskStatus, Tenant
from ai_org_backend.models.chat import ChatRole
from ai_org_backend.services.deep_research import run_deep_research
from ai_org_backend.services.storage import register_artefact
from ai_org_backend.utils.llm import chat

logger = logging.getLogger(__name__)

ARCHITECT_MODEL = "o3"
PROMPT_NAME = "architect.j2"
PROMPT_FEEDBACK_NAME = "architect_feedback.j2"

ARCHITECT_RUNS = prom_counter("ai_architect_runs_total", "Architect executions")
ARCHITECT_LATENCY = prom_hist("ai_architect_latency_seconds", "Architect latency")


def _message_content(resp: Any) -> str:
    if isinstance(resp, dict):
        return resp["choices"][0]["message"]["content"]
    return resp.choices[0].message.content  # type: ignore[index]


def _load_custom_template(session: Session, purpose: Purpose) -> str | None:
    task = session.exec(
        select(Task)
        .where(Task.purpose_id == purpose.id)
        .where(Task.description.ilike("architecture blueprint%"))
    ).first()
    if task and task.prompt_template:
        return task.prompt_template
    return None


def _build_architect_context(
    *,
    purpose: Purpose,
    tenant: Tenant | None,
    task: str | None = None,
) -> dict[str, str]:
    ctx = {"purpose": purpose.name, "task": task or "n/a", "external_references": ""}
    if tenant and tenant.allow_web_research:
        query = (
            "Find best practices and recent high-quality references for building: "
            f"{purpose.name}. Focus on architecture, security, scalability, and representative "
            "open-source examples."
        )
        research = run_deep_research(tenant.id, query)
        refs = [f"- {src['title']} ({src['url']})" for src in research.get("sources", [])][:5]
        if refs:
            ctx["external_references"] = "\n".join(refs)
    return ctx


def _render_prompt(template_name: str, context: dict[str, str]) -> str:
    template = load_template(template_name)
    return template.render(**context)


def run_architect(purpose: Purpose, task: str | None = None) -> str:
    """Generate an architecture blueprint for the given purpose."""

    start = time.time()
    template_name = PROMPT_NAME
    tenant: Tenant | None = None
    with SessionLocal() as session:
        fresh = session.get(Purpose, purpose.id)
        if not fresh:
            logger.error("Purpose %s not found for run_architect", purpose.id)
            return "⚠️ Purpose not found; cannot generate architecture blueprint."
        tenant = session.get(Tenant, fresh.tenant_id)
        custom_template = _load_custom_template(session, fresh)
        if custom_template:
            template_name = custom_template
        purpose = fresh
    ctx = _build_architect_context(purpose=purpose, tenant=tenant, task=task)
    try:
        prompt = _render_prompt(template_name, ctx)
    except Exception:
        logger.warning("Prompt %s not found; falling back to default", template_name)
        prompt = _render_prompt(PROMPT_NAME, ctx)

    try:
        resp = chat(
            model=ARCHITECT_MODEL,
            messages=[{"role": ChatRole.USER.value, "content": prompt}],
            tenant_id=purpose.tenant_id,
        )
        ARCHITECT_RUNS.inc()
        return _message_content(resp)
    finally:
        ARCHITECT_LATENCY.observe(time.time() - start)


def run_architect_feedback(
    purpose: Purpose, feedback: str, current_blueprint: str
) -> str:
    """Update the architecture blueprint using reviewer feedback."""

    start = time.time()
    with SessionLocal() as session:
        fresh = session.get(Purpose, purpose.id)
        if not fresh:
            logger.error("Purpose %s not found for run_architect_feedback", purpose.id)
            return "⚠️ Purpose not found; cannot update architecture blueprint."
        purpose = fresh
    ctx = {
        "purpose": purpose.name,
        "feedback": feedback,
        "current_blueprint": current_blueprint,
    }
    prompt = _render_prompt(PROMPT_FEEDBACK_NAME, ctx)
    try:
        resp = chat(
            model=ARCHITECT_MODEL,
            messages=[{"role": ChatRole.USER.value, "content": prompt}],
            tenant_id=purpose.tenant_id,
        )
        ARCHITECT_RUNS.inc()
        return _message_content(resp)
    finally:
        ARCHITECT_LATENCY.observe(time.time() - start)


@shared_task(name="agent.architect")
def architect_task(tenant_id: str, task_id: str, *args, **kwargs) -> None:
    """Celery entry point for the architect agent."""

    logger.info("[Architect] Starting task %s for tenant %s", task_id, tenant_id)
    with SessionLocal() as session:
        task_obj = session.get(Task, task_id)
        purpose = session.get(Purpose, task_obj.purpose_id) if task_obj and task_obj.purpose_id else None
    if not task_obj or not purpose:
        logger.error("[Architect] Missing task or purpose for task %s", task_id)
        return

    try:
        blueprint = run_architect(purpose, task=task_obj.description)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("[Architect] Generation failed for task %s: %s", task_id, exc)
        blueprint = f"ERROR: {exc}"

    register_artefact(
        task_id,
        blueprint.encode("utf-8"),
        filename="architecture_blueprint.md",
        media_type="text/markdown",
    )
    Repo(tenant_id).update(
        task_id,
        status=TaskStatus.DONE,
        owner=TaskOwner.ARCHITECT,
        notes="Blueprint generated",
    )
    logger.info("[Architect] Completed task %s", task_id)


@shared_task(name="architect.seed_graph", queue="architect")
def seed_graph(tenant_id: str, purpose_id: str) -> None:
    """Legacy helper used by seed scripts."""

    from ai_org_backend.agents.planner import run_planner
    from ai_org_backend.scripts.seed_graph import ingest

    with SessionLocal() as db:
        purpose = db.get(Purpose, purpose_id)
        if not purpose:
            logger.error("[Architect] Purpose %s not found for seed_graph", purpose_id)
            return
        blueprint = run_architect(purpose)
        tasks = run_planner(blueprint, tenant_id=tenant_id, purpose_id=purpose_id)
        id_map: dict[str, str] = {}
        for t in tasks:
            obj = Task(
                tenant_id=tenant_id,
                purpose_id=purpose_id,
                description=t["description"],
                business_value=t["business_value"],
                tokens_plan=t["tokens_plan"],
                purpose_relevance=t["purpose_relevance"],
            )
            db.add(obj)
            db.flush()
            id_map[t["id"]] = obj.id
        db.commit()

        for t in tasks:
            dep_id = t.get("depends_on") or t.get("depends_on_id")
            if dep_id and dep_id in id_map:
                db.add(
                    TaskDependency(
                        from_id=id_map[dep_id],
                        to_id=id_map[t["id"]],
                        dependency_type="FINISH_START",
                    )
                )
        db.commit()

    ingest(tenant_id)
