from __future__ import annotations

import time
from pathlib import Path

from jinja2 import Template
from ai_org_backend.utils.llm import chat
from celery import shared_task

from ai_org_backend.db import SessionLocal
from ai_org_backend.models import Purpose, Task, TaskDependency
from ai_org_backend.metrics import prom_counter, prom_hist


ARCHITECT_RUNS = prom_counter("ai_architect_runs_total", "Architect executions")
ARCHITECT_LATENCY = prom_hist("ai_architect_latency_seconds", "Architect latency")

PROMPT_TMPL = Template(Path("prompts/architect.j2").read_text())


def run_architect(purpose: Purpose, task: str | None = None) -> str:
    """Render template prompt and call OpenAI to produce an architecture blueprint."""
    prompt = PROMPT_TMPL.render(purpose=purpose.name, task=task or "n/a")
    start = time.time()
    try:
        resp = chat(
            model="o3",
            messages=[{"role": "user", "content": prompt}],
        )
        ARCHITECT_RUNS.inc()
    finally:
        ARCHITECT_LATENCY.observe(time.time() - start)

    content = resp.choices[0].message.content
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

