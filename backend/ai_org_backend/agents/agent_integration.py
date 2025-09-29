from __future__ import annotations

import logging

from ai_org_backend.db import SessionLocal
from ai_org_backend.main import TASK_CNT
from ai_org_backend.models import Task
from ai_org_backend.services.storage import register_artefact
from ai_org_backend.tasks.celery_app import celery


@celery.task(name="agent.integration")
def agent_integration(tenant_id: str, task_id: str) -> None:
    """Dummy integration agent: finalize integration of all artifacts."""
    logging.info(f"[IntegrationAgent] Starting integration for task {task_id} (tenant {tenant_id})")
    with SessionLocal() as session:
        task = session.get(Task, task_id)
        if not task:
            logging.error(f"[IntegrationAgent] Task {task_id} not found for integration")
            return
        content = f"Integration completed for task {task_id}."
        register_artefact(
            task_id,
            content.encode("utf-8"),
            filename="reports/integration_report.md",
            allow_overwrite=True,
        )
        task.status = "done"
        task.owner = "Integration"
        task.notes = "integration done"
        session.add(task)
        session.commit()
    TASK_CNT.labels(tenant_id, "integration", "done").inc()
    logging.info(f"[IntegrationAgent] Task {task_id} marked as done by integration agent")
