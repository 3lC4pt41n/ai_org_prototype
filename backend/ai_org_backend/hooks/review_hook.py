"""
Review Hook (monkey-patch register_artefact)
-------------------------------------------
We hook into `register_artefact` so that **whenever** the architecture blueprint
Markdown is saved, we:
  1) create (or reuse) a gating task "Architecture & Domain Review"
  2) wire dependencies: blueprint -> review -> all other tasks
  3) enqueue a Celery job to generate the review Markdown artefact

This avoids invasive edits to pipeline/orchestrator and stays tenant-safe.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, cast

from ai_org_backend.agents.reviewer import reviewer_task
from ai_org_backend.db import SessionLocal
from ai_org_backend.models import Artifact, Purpose, Task, TaskDependency, TaskOwner
from sqlmodel import select
from ai_org_backend.services import storage as _storage

# Keep original pointer so we can call it
_orig_register_artefact = _storage.register_artefact


_SKIP_REVIEW_DEPENDENCY = {
    "product requirements document",
    "architecture blueprint",
    "architecture & domain review",
}


def _ensure_review_task(tenant_id: str, purpose_id: str) -> Task:
    """
    Return existing or create a new "Architecture & Domain Review" task.
    Starts as todo/awaiting_approval; downstream is blocked until user approves.
    """
    with SessionLocal() as s:
        # Try to find an existing review task for this purpose
        t = s.exec(
            select(Task).where(
                Task.tenant_id == tenant_id,
                Task.purpose_id == purpose_id,
                Task.description == "Architecture & Domain Review",
            )
        ).first()
        if t:
            return t
        # Create a new review task
        t = Task(
            tenant_id=tenant_id,
            purpose_id=purpose_id,
            description="Architecture & Domain Review",
            business_value=0.0,
            tokens_plan=0,
            purpose_relevance=1.0,
            status="todo",
            owner=TaskOwner.REVIEW,
            notes="awaiting_approval",
        )
        s.add(t)
        s.commit()
        s.refresh(t)
        return t


def _wire_dependencies_after_blueprint(
    tenant_id: str, purpose_id: str, blueprint_task_id: str, review_task_id: str
) -> None:
    """
    Ensure: blueprint -> review, and review -> every other task in this purpose
    (except blueprint, review). This guarantees no implementation proceeds
    before review approval. Idempotent: skips existing edges.
    """
    with SessionLocal() as s:
        # Edge: blueprint -> review
        edge = s.exec(
            select(TaskDependency.id).where(
                TaskDependency.from_id == blueprint_task_id,
                TaskDependency.to_id == review_task_id,
            )
        ).first()
        if edge is None:
            s.add(
                TaskDependency(
                    from_id=blueprint_task_id,
                    to_id=review_task_id,
                    dependency_type="FINISH_START",
                )
            )
            s.commit()

        # Edge(s): review -> all other tasks (repo init + dev + anything else)
        other_tasks = s.exec(
            select(Task).where(Task.tenant_id == tenant_id, Task.purpose_id == purpose_id)
        ).all()
        for t in other_tasks:
            if t.id in (blueprint_task_id, review_task_id):
                continue
            desc = (t.description or "").strip().lower()
            if desc in _SKIP_REVIEW_DEPENDENCY:
                continue
            # Skip if edge already exists
            exists = s.exec(
                select(TaskDependency.id).where(
                    TaskDependency.from_id == review_task_id,
                    TaskDependency.to_id == t.id,
                )
            ).first()
            if exists is None:
                s.add(
                    TaskDependency(
                        from_id=review_task_id,
                        to_id=t.id,
                        dependency_type="FINISH_START",
                    )
                )
        s.commit()


def _schedule_reviewer_job(
    tenant_id: str, purpose_id: str, blueprint_task_id: str, review_task_id: str
) -> None:
    """
    Enqueue Celery job. We rely on the default 'celery' queue to keep this portable.
    """
    try:
        reviewer_task.delay(tenant_id, review_task_id, purpose_id, blueprint_task_id)
        logging.info(
            "[ReviewHook] Enqueued reviewer job (tenant=%s, purpose=%s)", tenant_id, purpose_id
        )
    except Exception as e:
        logging.error("[ReviewHook] Failed to enqueue reviewer job: %s", e)


def _maybe_trigger_review(task_id: str, filename: str) -> None:
    """
    Detect if this artefact is the architecture blueprint. If yes, set up the review gate.
    """
    # Heuristics: path contains 'blueprints' and file ends with 'architecture_blueprint.md'
    fname = filename.replace("\\", "/")
    is_blueprint = ("blueprints" in fname) and fname.endswith("architecture_blueprint.md")
    if not is_blueprint:
        return

    with SessionLocal() as s:
        task = s.get(Task, task_id)
        if not task:
            return
        tenant_id = task.tenant_id
        purpose_id = task.purpose_id
        purpose = s.get(Purpose, purpose_id) if purpose_id else None
        purpose_mode = (getattr(purpose, "mode", None) or "manual").lower()
        latest_blueprint_artifact = s.exec(
            select(Artifact)
            .where(Artifact.task_id == task_id)
            .order_by(Artifact.created_at.desc())
        ).first()
        blueprint_released = bool(
            latest_blueprint_artifact and latest_blueprint_artifact.released
        )

    # Manual mode must wait for explicit architecture approval.
    if purpose_mode == "manual" and not blueprint_released:
        logging.info(
            "[ReviewHook] Skip auto-review for purpose=%s (manual mode, blueprint not released)",
            purpose_id,
        )
        return

    # Create or reuse review task
    review_task = _ensure_review_task(tenant_id, purpose_id)
    # Avoid scheduling duplicate reviewer jobs if artefact already exists
    with SessionLocal() as s2:
        existing_artifact = (
            s2.query(Artifact).filter(Artifact.task_id == review_task.id).first()
        )
    if existing_artifact:
        logging.info(
            "[ReviewHook] Review artefact already exists for task=%s, skipping reviewer job",
            review_task.id,
        )
        return
    # Wire dependency edges
    _wire_dependencies_after_blueprint(
        tenant_id, purpose_id, blueprint_task_id=task_id, review_task_id=review_task.id
    )
    # Fire reviewer job (generates markdown artefact; leaves task 'todo')
    _schedule_reviewer_job(
        tenant_id, purpose_id, blueprint_task_id=task_id, review_task_id=review_task.id
    )


def register_artefact_with_review(
    task_id: str,
    data: bytes,
    filename: str,
    allow_overwrite: bool = False,
    media_type: Optional[str] = None,
):
    """
    Wrapper around the original register_artefact.
    Calls the original, then triggers review if the blueprint was saved.

    Args:
        task_id: The ID of the task the artefact belongs to.
        data: The artefact contents.
        filename: Target filename for the artefact.
        allow_overwrite: Whether to allow overwriting existing artefacts.
        media_type: Optional media type for the artefact; forwarded to the
            underlying storage implementation.
    """
    result = _orig_register_artefact(
        task_id,
        data,
        filename,
        allow_overwrite=allow_overwrite,
        media_type=media_type,
    )
    try:
        _maybe_trigger_review(task_id=task_id, filename=filename)
    except Exception as e:
        # Never break artefact saving; just log
        logging.error("[ReviewHook] Trigger failed for task=%s file=%s: %s", task_id, filename, e)
    return result


# ---- Apply monkey-patch on import -------------------------------------------
_storage.register_artefact = cast(Any, register_artefact_with_review)
_storage.save_artefact = cast(Any, register_artefact_with_review)
