from __future__ import annotations

import time
from pathlib import Path

from ai_org_backend.db import SessionLocal
from ai_org_backend.metrics import prom_counter, prom_hist
from ai_org_backend.models import Purpose, Task, TaskDependency, Tenant
from ai_org_backend.services.deep_research import run_deep_research
from ai_org_backend.services.llm_client import MODEL_PRO, chat_with_tools
from celery import shared_task
from jinja2 import Template

ARCHITECT_RUNS = prom_counter("ai_architect_runs_total", "Architect executions")
ARCHITECT_LATENCY = prom_hist("ai_architect_latency_seconds", "Architect latency")

PROMPT_TMPL = Template(Path("prompts/architect.j2").read_text())


def run_architect(purpose: Purpose, task: str | None = None) -> str:
    """Render template prompt and call OpenAI to produce an architecture blueprint.

    If the tenant opted in, a short deep-research step is executed first and
    references are injected into the prompt.
    """
    ctx = {"purpose": purpose.name, "task": task or "n/a", "external_references": ""}

    allow_research = False
    with SessionLocal() as db:
        tenant = db.get(Tenant, purpose.tenant_id)
        allow_research = bool(tenant and tenant.allow_web_research)

    if allow_research:
        q = (
            f"Find best practices and recent high-quality references for building: {purpose.name}. "
            "Focus on architecture, security, scalability, and representative open-source examples."
        )
        research = run_deep_research(purpose.tenant_id, q, model=MODEL_PRO)
        refs_lines = [f"- {s['title']} ({s['url']})" for s in research["sources"]][:5]
        ctx["external_references"] = "\n".join(refs_lines)

    prompt = PROMPT_TMPL.render(**ctx)
    start = time.time()
    try:
        resp = chat_with_tools(
            messages=[{"role": "user", "content": prompt}],
            model=MODEL_PRO,
            tenant=purpose.tenant_id,
        )
        ARCHITECT_RUNS.inc()
    finally:
        ARCHITECT_LATENCY.observe(time.time() - start)

    if not resp:
        return ""
    content = resp["choices"][0]["message"]["content"]
    return content


@shared_task(name="architect.seed_graph", queue="architect")
def seed_graph(tenant_id: str, purpose_id: str) -> None:
    from ai_org_backend.scripts.seed_graph import ingest

    with SessionLocal() as db:
        purpose = db.get(Purpose, purpose_id)
        blueprint = run_architect(purpose)
        # Generate structured task list using planner
        from ai_org_backend.agents.planner import run_planner

        tasks = run_planner(blueprint)
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
