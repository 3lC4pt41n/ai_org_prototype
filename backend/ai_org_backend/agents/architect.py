from __future__ import annotations

import time

import logging
from celery import shared_task
from sqlmodel import select

from .utils import load_template

from ai_org_backend.db import SessionLocal
from ai_org_backend.models import Purpose, Task, TaskDependency, Tenant
from ai_org_backend.metrics import prom_counter, prom_hist
from ai_org_backend.services.llm_client import chat_with_tools, MODEL_PRO
from ai_org_backend.services.deep_research import run_deep_research
from ai_org_backend.services.budget import BudgetExceededError
from ai_org_backend.services.storage import save_artefact
from ai_org_backend.models.chat import ChatRole


ARCHITECT_RUNS = prom_counter("ai_architect_runs_total", "Architect executions")
ARCHITECT_LATENCY = prom_hist("ai_architect_latency_seconds", "Architect latency")

PROMPT_TMPL = load_template("architect.j2")
PROMPT_FEEDBACK_TMPL = load_template("architect_feedback.j2")

logger = logging.getLogger(__name__)


def run_architect(purpose: Purpose, task: str | None = None) -> str:
    """Render template prompt and call OpenAI to produce an architecture blueprint."""

    allow_research = False
    template_key: str | None = None
    with SessionLocal() as db:
        fresh_purpose = db.get(Purpose, purpose.id)
        if not fresh_purpose:
            logger.error("Purpose %s not found for run_architect", purpose.id)
            return "⚠️ Purpose not found; cannot generate architecture blueprint."
        tenant = db.get(Tenant, fresh_purpose.tenant_id)
        allow_research = bool(tenant and tenant.allow_web_research)
        purpose_name = fresh_purpose.name
        tenant_id = fresh_purpose.tenant_id
        arch_task = db.exec(
            select(Task)
            .where(Task.purpose_id == fresh_purpose.id)
            .where(Task.description.ilike("architecture blueprint%"))
        ).first()
        if arch_task and arch_task.prompt_template:
            template_key = arch_task.prompt_template

    ctx = {"purpose": purpose_name, "task": task or "n/a", "external_references": ""}

    if allow_research:
        q = (
            f"Find best practices and recent high-quality references for building: {purpose_name}. "
            "Focus on architecture, security, scalability, and representative open-source examples."
        )
        research = run_deep_research(tenant_id, q, model=MODEL_PRO)
        refs_lines = [f"- {s['title']} ({s['url']})" for s in research["sources"]][:5]
        ctx["external_references"] = "\n".join(refs_lines)

    prompt_template = PROMPT_TMPL
    if template_key:
        try:
            prompt_template = load_template(template_key)
        except FileNotFoundError:
            logger.warning(
                "Custom architecture prompt %s not found; using default", template_key
            )
        except Exception:
            logger.exception("Failed to load custom architecture prompt %s", template_key)
    prompt = prompt_template.render(**ctx)
    start = time.time()
    try:
        resp = chat_with_tools(
            messages=[{"role": ChatRole.USER.value, "content": prompt}],
            model=MODEL_PRO,
            tenant_id=tenant_id,
            usage_label="architect",
        )
        ARCHITECT_RUNS.inc()
        content = resp["choices"][0]["message"]["content"]
        return content
    except BudgetExceededError:
        logger.error("Budget exhausted during architecture planning for tenant %s", tenant_id)
        return "\u26d4 Budget exhausted. Architecture step skipped."
    finally:
        ARCHITECT_LATENCY.observe(time.time() - start)


def run_architect_feedback(purpose: Purpose, feedback: str, current_blueprint: str) -> str:
    """Update existing architecture blueprint based on user feedback."""

    with SessionLocal() as db:
        fresh_purpose = db.get(Purpose, purpose.id)
        if not fresh_purpose:
            logger.error("Purpose %s not found for run_architect_feedback", purpose.id)
            return "⚠️ Purpose not found; cannot update architecture blueprint."
        purpose_name = fresh_purpose.name
        tenant_id = fresh_purpose.tenant_id

    ctx = {
        "purpose": purpose_name,
        "feedback": feedback,
        "current_blueprint": current_blueprint,
    }
    prompt = PROMPT_FEEDBACK_TMPL.render(**ctx)
    start = time.time()
    try:
        resp = chat_with_tools(
            messages=[{"role": ChatRole.USER.value, "content": prompt}],
            model=MODEL_PRO,
            tenant_id=tenant_id,
            usage_label="architect_feedback",
        )
        ARCHITECT_RUNS.inc()
        content = resp["choices"][0]["message"]["content"]
        return content
    except BudgetExceededError:
        return "⚠️ Budget exhausted during architecture update."
    finally:
        ARCHITECT_LATENCY.observe(time.time() - start)


@shared_task(name="architect.seed_graph", queue="architect")
def seed_graph(tenant_id: str, purpose_id: str) -> None:
    from ai_org_backend.scripts.seed_graph import ingest

    with SessionLocal() as db:
        purpose = db.get(Purpose, purpose_id)
        blueprint = run_architect(purpose)
        # Generate structured task list using planner
        from ai_org_backend.agents.planner import run_planner
        tasks = run_planner(blueprint, tenant_id=tenant_id, purpose_id=purpose_id)
        # Persist tasks in the database
        id_map = {}
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
            id_map[t["id"]] = obj.id
        db.commit()

        for t in tasks:
            dep_id = t.get("depends_on") or t.get("depends_on_id")
            if dep_id and dep_id in id_map:
                db.add(TaskDependency(from_id=id_map[dep_id], to_id=id_map[t["id"]]))
        db.commit()

    ingest(tenant_id)

