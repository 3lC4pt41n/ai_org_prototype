from __future__ import annotations

import json
import time
from pathlib import Path

from jinja2 import Template
from openai import OpenAI
from celery import shared_task

from ai_org_backend.db import SessionLocal
from ai_org_backend.models import Purpose, Task, TaskDependency
from ai_org_backend.metrics import prom_counter, prom_hist


ARCHITECT_RUNS = prom_counter("ai_architect_runs_total", "Architect executions")
ARCHITECT_LATENCY = prom_hist("ai_architect_latency_seconds", "Architect latency")

PROMPT_TMPL = Template(Path("prompts/architect.j2").read_text())


def run_architect(purpose: Purpose, task: str | None = None) -> dict:
    """Render template prompt and call OpenAI."""
    prompt = PROMPT_TMPL.render(purpose=purpose.name, task=task or "n/a")
    client = OpenAI()
    start = time.time()
    try:
        resp = client.chat.completions.create(
            model="o3",
            messages=[{"role": "user", "content": prompt}],
        )
        ARCHITECT_RUNS.inc()
    finally:
        ARCHITECT_LATENCY.observe(time.time() - start)

    payload = json.loads(resp.choices[0].message.content)
    return payload


@shared_task(name="architect.seed_graph", queue="architect")
def seed_graph(tenant_id: str, purpose_id: str) -> None:
    from ai_org_backend.scripts.seed_graph import ingest

    with SessionLocal() as db:
        purpose = db.get(Purpose, purpose_id)
        data = run_architect(purpose)

        for t in data["tasks"]:
            obj = Task(
                id=t["id"],
                tenant_id=tenant_id,
                purpose_id=purpose_id,
                description=t["description"],
                business_value=t["business_value"],
                tokens_plan=t["tokens_plan"],
                purpose_relevance=t["purpose_relevance"],
            )
            db.add(obj)
        db.commit()

        for t in data["tasks"]:
            if t.get("depends_on"):
                db.add(
                    TaskDependency(
                        from_id=t["id"],
                        to_id=t["depends_on"],
                        kind="hard_blocker",
                        source="architect",
                    )
                )
        db.commit()

    ingest(tenant_id)

