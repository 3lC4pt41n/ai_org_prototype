from __future__ import annotations

import logging

from ai_org_backend.db import SessionLocal
from ai_org_backend.main import TASK_CNT
from ai_org_backend.models import Task, TaskOwner
from ai_org_backend.services.storage import register_artefact
from ai_org_backend.tasks.celery_app import celery


@celery.task(name="agent.insight")
def agent_insight(tenant_id: str, task_id: str) -> None:
    """Dummy insight agent: generate a summary of insights."""
    logging.info(f"[InsightAgent] Generating insights for task {task_id} (tenant {tenant_id})")
    with SessionLocal() as session:
        task = session.get(Task, task_id)
        if not task:
            logging.error(f"[InsightAgent] Task {task_id} not found for insight generation")
            return
        insight_md = "# Insights Report\nKeine besonderen Erkenntnisse."
        register_artefact(
            task_id,
            insight_md.encode("utf-8"),
            filename="reports/insights_report.md",
            allow_overwrite=True,
        )
        task.status = "done"
        task.owner = TaskOwner.INSIGHT
        task.notes = "insights generated"
        session.add(task)
        session.commit()
    TASK_CNT.labels(tenant_id, "insight", "done").inc()
    logging.info(f"[InsightAgent] Task {task_id} completed by insight agent")
