"""
E2E / UAT Test Agent
--------------------
Derives pytest-based E2E tests from PRD acceptance criteria, optionally using Playwright.
Runs the tests and raises fix tasks on failure.
"""

from __future__ import annotations

import os

from sqlalchemy import desc

from ai_org_backend.db import SessionLocal
from ai_org_backend.metrics import prom_counter, prom_hist
from ai_org_backend.models import Artefact, Purpose, Task
from ai_org_backend.models.chat import ChatRole
from ai_org_backend.services.llm_client import MODEL_PRO, chat_with_tools
from ai_org_backend.services.storage import save_artefact
from ai_org_backend.services.test_exec import ensure_playwright, run_pytest
from ai_org_backend.tasks.celery_app import celery

from .utils import load_template

RUNS = prom_counter("ai_e2e_runs_total", "E2E agent executions")
LAT = prom_hist("ai_e2e_latency_seconds", "E2E agent latency")

TEMPLATE = load_template("e2e_tests.j2")


def _load_latest_prd(s, purpose_id: str) -> str:
    q = (
        s.query(Artefact)
        .join(Task, Task.id == Artefact.task_id)
        .filter(Task.purpose_id == purpose_id)
        .filter(Artefact.filename.endswith("requirements/product_requirements.md"))
        .order_by(desc(Artefact.created_at))
    )
    a = q.first()
    return (a.blob.decode("utf-8", errors="ignore") if a and a.blob else "").strip()


@celery.task(name="agent.e2e")
def e2e_task(tenant_id: str, task_id: str) -> None:
    import time

    start = time.time()
    with SessionLocal() as s:
        task = s.get(Task, task_id)
        if not task:
            return
        purpose = s.get(Purpose, task.purpose_id)
        if not purpose:
            return
        prd_md = _load_latest_prd(s, purpose.id)
        api_base = os.getenv("API_BASE_URL", "")
        ui_base = os.getenv("UI_BASE_URL", "")
        prompt = TEMPLATE.render(
            purpose_name=purpose.name,
            api_base_url=api_base,
            ui_base_url=ui_base,
            prd_md=prd_md,
        )
    try:
        resp = chat_with_tools(
            messages=[{"role": ChatRole.USER.value, "content": prompt}],
            model=MODEL_PRO,
            temperature=0,
            tenant_id=tenant_id,
        )
        RUNS.inc()
        content = (
            resp["choices"][0]["message"]["content"]
            if resp
            else "# Skipped\nReason: budget exhausted."
        )
    finally:
        LAT.observe(time.time() - start)

    # Store test file
    test_rel = f"tests/e2e/test_e2e_{task_id}.py"
    save_artefact(task_id, content.encode("utf-8"), filename=test_rel, allow_overwrite=True)

    # Try ensure playwright (best effort, will skip tests internally if not present)
    ensure_playwright()
    rc, out, err = run_pytest(paths=["tests/e2e"], marker="e2e", extra_args=["-q"])
    results = (out or "") + ("\n" + err if err else "")
    save_artefact(
        task_id, results.encode("utf-8"), filename="reports/e2e_results.txt", allow_overwrite=True
    )

    with SessionLocal() as s:
        if rc == 0:
            t = s.get(Task, task_id)
            t.status = "done"
            t.owner = "QA-E2E"
            t.notes = "e2e passed"
            s.add(t)
            s.commit()
        else:
            t = s.get(Task, task_id)
            t.status = "failed"
            t.owner = "QA-E2E"
            t.notes = "e2e failures"
            s.add(t)
            s.commit()
            fix = Task(
                tenant_id=tenant_id,
                purpose_id=t.purpose_id,
                description="Fix E2E / Acceptance Failures",
                business_value=1.0,
                tokens_plan=1000,
                purpose_relevance=1.0,
                notes=results[:2000],
            )
            s.add(fix)
            s.commit()
