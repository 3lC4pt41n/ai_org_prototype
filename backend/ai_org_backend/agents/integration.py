"""
Integration Test Agent
----------------------
Generates pytest-based integration tests (black-box over HTTP and optional UI),
executes them, stores results, and raises fix tasks on failure.
"""

from __future__ import annotations

import os
from pathlib import Path

from jinja2 import Template

from ai_org_backend.db import SessionLocal
from ai_org_backend.metrics import prom_counter, prom_hist
from ai_org_backend.models import Artefact, Purpose, Task
from ai_org_backend.services.llm_client import MODEL_PRO, chat_with_tools
from ai_org_backend.services.storage import save_artefact
from ai_org_backend.services.test_exec import run_pytest
from ai_org_backend.tasks.celery_app import celery

RUNS = prom_counter("ai_integration_runs_total", "Integration agent executions")
LAT = prom_hist("ai_integration_latency_seconds", "Integration agent latency")

TEMPLATE = Template(Path("prompts/integration_tests.j2").read_text(encoding="utf-8"))


def _load_latest_text_artifact(s, purpose_id: str, path_suffix: str) -> str:
    """Fetch last artefact whose filename ends with given suffix under same purpose."""
    q = (
        s.query(Artefact)
        .join(Task, Task.id == Artefact.task_id)
        .filter(Task.purpose_id == purpose_id)
        .filter(Artefact.filename.endswith(path_suffix))
        .order_by(Artefact.created_at.desc())
    )
    a = q.first()
    return (a.blob.decode("utf-8", errors="ignore") if a and a.blob else "").strip()


@celery.task(name="agent.integration")
def integration_task(tenant_id: str, task_id: str) -> None:
    """
    Generate & run integration tests for this purpose. `task_id` is the Integration Tests task.
    """
    import time

    start = time.time()
    with SessionLocal() as s:
        task = s.get(Task, task_id)
        if not task:
            return
        purpose = s.get(Purpose, task.purpose_id)
        if not purpose:
            return
        prd_md = _load_latest_text_artifact(s, purpose.id, "requirements/product_requirements.md")
        blueprint_md = _load_latest_text_artifact(
            s, purpose.id, "blueprints/architecture_blueprint.md"
        )
        api_base = os.getenv("API_BASE_URL", "")
        ui_base = os.getenv("UI_BASE_URL", "")
        prompt = TEMPLATE.render(
            purpose_name=purpose.name,
            api_base_url=api_base,
            ui_base_url=ui_base,
            prd_md=prd_md,
            blueprint_md=blueprint_md,
        )
    try:
        resp = chat_with_tools(
            messages=[{"role": "user", "content": prompt}],
            model=MODEL_PRO,
            temperature=0,
            tenant=tenant_id,
        )
        RUNS.inc()
        if not resp:
            content = "# Skipped\nReason: budget exhausted."
        else:
            content = resp["choices"][0]["message"]["content"]
    finally:
        LAT.observe(time.time() - start)

    # Store test file artefact
    test_rel = f"tests/integration/test_integration_{task_id}.py"
    save_artefact(task_id, content.encode("utf-8"), filename=test_rel, allow_overwrite=True)

    # Execute pytest on integration tests
    rc, out, err = run_pytest(paths=["tests/integration"], marker="integration", extra_args=["-q"])
    results = (out or "") + ("\n" + err if err else "")
    save_artefact(
        task_id,
        results.encode("utf-8"),
        filename="reports/integration_results.txt",
        allow_overwrite=True,
    )

    with SessionLocal() as s:
        # Mark status + spawn fix task on failure
        if rc == 0:
            t = s.get(Task, task_id)
            t.status = "done"
            t.owner = "QA-Integration"
            t.notes = "integration passed"
            s.add(t)
            s.commit()
        else:
            t = s.get(Task, task_id)
            t.status = "failed"
            t.owner = "QA-Integration"
            t.notes = "integration failures"
            s.add(t)
            s.commit()
            # Create fix task
            fix = Task(
                tenant_id=tenant_id,
                purpose_id=t.purpose_id,
                description="Fix Integration Failures",
                business_value=1.0,
                tokens_plan=800,
                purpose_relevance=1.0,
                notes=results[:2000],
            )
            s.add(fix)
            s.commit()
