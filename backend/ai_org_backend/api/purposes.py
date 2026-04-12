import logging
import shutil
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, update
from sqlmodel import Session, select

from ai_org_backend.api.dependencies import get_current_tenant
from ai_org_backend.db import engine
from ai_org_backend.models import (
    Artifact,
    Purpose,
    Task,
    Tenant,
)
from ai_org_backend.redis_client import pool
from ai_org_backend.services import graph_sync
from ai_org_backend.services.storage import retract_artifact
from ai_org_backend.settings import settings

router = APIRouter(prefix="/api/purposes", tags=["purposes"])


@router.post("/{purpose_id}/activate")
def activate_purpose(purpose_id: str, current_tenant: Tenant = Depends(get_current_tenant)):
    tenant_id = current_tenant.id
    with Session(engine) as session:
        session.exec(update(Purpose).where(Purpose.tenant_id == tenant_id).values(is_active=False))
        purpose = session.get(Purpose, purpose_id)
        if not purpose or purpose.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="Purpose not found")
        purpose.is_active = True
        session.add(purpose)
        session.commit()
    return {"status": "activated", "purpose_id": purpose_id}


@router.post("/{purpose_id}/pause")
def pause_purpose(purpose_id: str, current_tenant: Tenant = Depends(get_current_tenant)):
    tenant_id = current_tenant.id
    with Session(engine) as session:
        purpose = session.get(Purpose, purpose_id)
        if not purpose or purpose.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="Purpose not found")
    try:
        pool.set(f"pause:{tenant_id}:{purpose_id}", "1")
    except Exception as e:
        logging.error("Failed to set pause flag: %s", e)
    return {"status": "paused"}


@router.post("/{purpose_id}/start")
def start_purpose(purpose_id: str, current_tenant: Tenant = Depends(get_current_tenant)):
    """Resume a paused purpose (idempotent)."""

    tenant_id = current_tenant.id
    with Session(engine) as session:
        purpose = session.get(Purpose, purpose_id)
        if not purpose or purpose.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="Purpose not found")

    try:
        pool.delete(f"pause:{tenant_id}:{purpose_id}")
    except Exception as e:
        logging.error("Failed to remove pause flag: %s", e)
    return {"status": "resumed"}


@router.patch("/{purpose_id}")
def update_purpose(
    purpose_id: str, payload: dict, current_tenant: Tenant = Depends(get_current_tenant)
):
    """Update a Purpose (toggle mode auto/manual).

    S6-#10.2: When mode flips to 'auto', dispatches Celery orchestration
    to auto-approve pending artifacts and advance the pipeline.
    """
    tenant_id = current_tenant.id
    with Session(engine) as session:
        purpose = session.get(Purpose, purpose_id)
        if not purpose or purpose.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="Purpose not found")
        old_mode = purpose.mode
        new_mode = payload.get("mode")
        if new_mode:
            if new_mode not in ("auto", "manual"):
                raise HTTPException(status_code=400, detail="Invalid mode value")
            purpose.mode = new_mode
        session.add(purpose)
        session.commit()
        session.refresh(purpose)

    # S6-#10.2: Trigger orchestration when switching to auto
    if new_mode == "auto" and old_mode != "auto":
        try:
            from ai_org_backend.tasks.celery_app import celery
            celery.send_task(
                "orchestrator.advance_purpose",
                args=[tenant_id, purpose_id],
                queue=f"{tenant_id}:orchestrator",
            )
            logging.info(
                "[S6-#10.2] Auto-mode activated for purpose %s — dispatching orchestrator",
                purpose_id,
            )
        except Exception as exc:
            logging.warning(
                "[S6-#10.2] Failed to dispatch auto-mode orchestrator: %s", exc
            )

    return {"purpose_id": purpose.id, "mode": purpose.mode}


def _collect_task_ids(session: Session, purpose_id: str, tenant_id: str) -> List[str]:
    """Return task IDs for the given purpose/tenant."""

    result = session.exec(
        select(Task.id).where(Task.purpose_id == purpose_id, Task.tenant_id == tenant_id)
    )
    return list(result)


def _collect_artifact_ids(session: Session, task_ids: List[str]) -> List[str]:
    if not task_ids:
        return []
    result = session.exec(select(Artifact.id).where(Artifact.task_id.in_(task_ids)))
    return list(result)


@router.delete("/{purpose_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_purpose(purpose_id: str, current_tenant: Tenant = Depends(get_current_tenant)) -> Response:
    """Delete a Purpose and all related records.

    CASCADE DELETE is enforced at the database level, so most cleanup happens
    automatically. This function handles external systems (vector store, Neo4j)
    and file system cleanup that the database cannot manage.
    """
    tenant_id = current_tenant.id
    with Session(engine) as session:
        purpose = session.get(Purpose, purpose_id)
        if not purpose or purpose.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="Purpose not found")

        # Collect IDs for external system cleanup (vector store, Neo4j, workspace)
        # CASCADE DELETE at DB level handles Task, TaskDependency, Artifact,
        # Feedback, ChatMessage, and ChatThreadContext automatically
        task_ids = _collect_task_ids(session, purpose_id, tenant_id)
        artifact_ids = _collect_artifact_ids(session, task_ids)

        # Retract artifacts from external systems (vector store + Neo4j)
        for artifact_id in artifact_ids:
            try:
                retract_artifact(artifact_id, remove_from_neo4j=True)
            except Exception as exc:  # pragma: no cover - best effort clean-up
                logging.error(
                    "Failed to retract artifact %s for purpose %s: %s",
                    artifact_id,
                    purpose_id,
                    exc,
                )

        # CASCADE DELETE handles all DB records automatically
        session.delete(purpose)
        session.commit()

    # Redis cleanup (best effort)
    try:
        if pool is not None:
            pool.delete(f"pause:{tenant_id}:{purpose_id}")
            pool.delete(f"budget:{tenant_id}:{purpose_id}")
            pool.delete(f"tokens:{tenant_id}:{purpose_id}")
    except Exception as exc:  # pragma: no cover - redis best effort
        logging.error("Failed to clear Redis keys for purpose %s: %s", purpose_id, exc)

    # Neo4j graph cleanup (best effort)
    try:
        graph_sync.remove_tasks(task_ids)
        graph_sync.remove_purpose(purpose_id)
    except Exception as exc:  # pragma: no cover - best effort cleanup
        logging.error("Failed to remove tasks from graph for purpose %s: %s", purpose_id, exc)

    # Workspace file cleanup (best effort)
    try:
        root = Path(settings.workspace_dir).resolve()
        candidate = (root / tenant_id / purpose_id).resolve()
        if str(candidate).startswith(str(root)):
            shutil.rmtree(candidate, ignore_errors=True)
    except Exception as exc:  # pragma: no cover
        logging.error("Failed to remove workspace for purpose %s: %s", purpose_id, exc)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
