"""Celery task handling architecture blueprint revisions."""

from __future__ import annotations

import logging

from celery import shared_task

from ai_org_backend.agents.architect import run_architect_feedback
from ai_org_backend.db import SessionLocal
from ai_org_backend.main import Repo
from ai_org_backend.models import Purpose, Task, TaskOwner, TaskStatus
from ai_org_backend.services.storage import register_artefact

logger = logging.getLogger(__name__)


@shared_task(name="agent.architect_feedback")
def architect_feedback_task(
    tenant_id: str,
    task_id: str,
    feedback: str,
    current_blueprint: str,
) -> None:
    """Apply feedback to an architecture blueprint and persist a new revision."""

    logger.info("[ArchitectFeedback] Starting task %s for tenant %s", task_id, tenant_id)
    with SessionLocal() as session:
        task_obj = session.get(Task, task_id)
        purpose = session.get(Purpose, task_obj.purpose_id) if task_obj and task_obj.purpose_id else None
    if not task_obj or not purpose:
        logger.error("[ArchitectFeedback] Missing task or purpose for task %s", task_id)
        return

    try:
        revision = run_architect_feedback(purpose, feedback, current_blueprint)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception(
            "[ArchitectFeedback] Generation failed for task %s: %s", task_id, exc
        )
        revision = f"ERROR: {exc}"

    register_artefact(
        task_id,
        revision.encode("utf-8"),
        filename="architecture_blueprint_revision.md",
        media_type="text/markdown",
    )
    Repo(tenant_id).update(
        task_id,
        status=TaskStatus.DONE,
        owner=TaskOwner.ARCHITECT,
        notes="Blueprint revised",
    )
    logger.info("[ArchitectFeedback] Completed task %s", task_id)
