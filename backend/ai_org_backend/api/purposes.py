import logging
import shutil
from typing import Iterable

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import or_, update
from sqlmodel import Session, delete, select

from ai_org_backend.api.dependencies import get_current_tenant
from ai_org_backend.db import engine
from ai_org_backend.models import (
    Artifact,
    ArtifactFeedback,
    ChatMessage,
    ChatMessageArtifact,
    ChatThreadContext,
    Feedback,
    Purpose,
    Task,
    TaskDependency,
    TaskOwner,
    Tenant,
)
from ai_org_backend.redis_client import pool
from ai_org_backend.repo import Repo
from ai_org_backend.scripts.seed_graph import ingest
from ai_org_backend.services.storage import register_artefact
from ai_org_backend.services import graph_sync
from ai_org_backend.settings import settings

router = APIRouter(prefix="/api/purposes", tags=["purposes"])
logger = logging.getLogger(__name__)


def _remove_workspace_dir(tenant_id: str, purpose_id: str) -> None:
    """Best-effort removal of the workspace directory for a purpose."""

    workspace_root = settings.workspace_dir.resolve()
    candidate = (workspace_root / tenant_id / purpose_id).resolve()
    if not str(candidate).startswith(str(workspace_root)):
        logger.warning("Refusing to delete workspace outside root: %s", candidate)
        return
    try:
        shutil.rmtree(candidate)
    except FileNotFoundError:
        return
    except Exception as exc:  # pragma: no cover - best effort cleanup
        logger.warning("Failed to remove workspace directory %s: %s", candidate, exc)


def _delete_related_records(session: Session, purpose_id: str) -> list[str]:
    """Remove all database rows tied to the given purpose.

    Returns the list of task IDs deleted so callers can mirror the change
    in external systems (e.g. Neo4j).
    """

    task_ids: list[str] = session.exec(
        select(Task.id).where(Task.purpose_id == purpose_id)
    ).all()
    if not task_ids:
        task_ids = []

    artifact_ids: list[str] = []
    if task_ids:
        artifact_ids = session.exec(
            select(Artifact.id).where(Artifact.task_id.in_(task_ids))
        ).all()
        if not artifact_ids:
            artifact_ids = []

    chat_ids: set[str] = set(
        session.exec(select(ChatMessage.id).where(ChatMessage.purpose_id == purpose_id)).all()
    )
    if task_ids:
        chat_ids.update(
            session.exec(select(ChatMessage.id).where(ChatMessage.task_id.in_(task_ids))).all()
        )
    if artifact_ids:
        chat_ids.update(
            session.exec(
                select(ChatMessageArtifact.chat_message_id).where(
                    ChatMessageArtifact.artifact_id.in_(artifact_ids)
                )
            ).all()
        )

    if artifact_ids:
        session.exec(
            delete(ArtifactFeedback).where(ArtifactFeedback.artifact_id.in_(artifact_ids))
        )
        session.exec(
            delete(ChatMessageArtifact).where(ChatMessageArtifact.artifact_id.in_(artifact_ids))
        )
        session.exec(delete(Artifact).where(Artifact.id.in_(artifact_ids)))

    if chat_ids:
        session.exec(
            delete(ChatMessageArtifact).where(ChatMessageArtifact.chat_message_id.in_(chat_ids))
        )
        session.exec(delete(ChatMessage).where(ChatMessage.id.in_(chat_ids)))

    if task_ids:
        session.exec(
            delete(TaskDependency).where(
                or_(
                    TaskDependency.from_id.in_(task_ids),
                    TaskDependency.to_id.in_(task_ids),
                )
            )
        )
        session.exec(delete(Task).where(Task.id.in_(task_ids)))

    session.exec(delete(Feedback).where(Feedback.purpose_id == purpose_id))
    session.exec(
        delete(ChatThreadContext).where(ChatThreadContext.purpose_id == purpose_id)
    )

    return task_ids


def _cleanup_graph(task_ids: Iterable[str], purpose_id: str) -> None:
    """Remove nodes and relationships in Neo4j for a deleted purpose."""

    ids = [tid for tid in task_ids if tid]
    try:
        if ids:
            graph_sync.delete_tasks(ids)
        graph_sync.delete_purpose(purpose_id)
    except Exception as exc:  # pragma: no cover - best effort cleanup
        logger.warning("Failed to clean up graph for purpose %s: %s", purpose_id, exc)


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
    """
    Start (or resume) a purpose.
    - Idempotent: if the PRD already exists, no 400 is raised; the pause flag is
      removed and 200 returned instead.
    - If no PRD exists yet, it is created.
    """

    tenant_id = current_tenant.id
    with Session(engine) as session:
        purpose = session.get(Purpose, purpose_id)
        if not purpose or purpose.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="Purpose not found")

        prd_task = session.exec(
            select(Task)
            .where(Task.purpose_id == purpose_id)
            .where(Task.description.ilike("%Product Requirements Document%"))
        ).first()

        prd_artifact = None
        if prd_task:
            prd_artifact = session.exec(
                select(Artifact).where(Artifact.task_id == prd_task.id)
            ).first()

        if prd_artifact:
            try:
                pool.delete(f"pause:{tenant_id}:{purpose_id}")
            except Exception as e:
                logging.error("Failed to remove pause flag: %s", e)
            return {"status": "resumed", "idempotent": True}

        prd_task_obj = Task(
            tenant_id=tenant_id,
            purpose_id=purpose_id,
            description="Product Requirements Document",
            status="done",
            owner=TaskOwner.PRODUCT_OWNER,
        )
        session.add(prd_task_obj)
        session.commit()
        session.refresh(prd_task_obj)

        prd_md = (
            f"# Product Requirements Document\n\n"
            f"**Purpose:** {purpose.name}\n\n"
            f"## Overview\n\nTBD\n"
        )
        register_artefact(
            prd_task_obj.id,
            prd_md.encode("utf-8"),
            filename="requirements/product_requirements_document.md",
            media_type="text/markdown",
            allow_overwrite=True,
        )
        Repo(tenant_id).update(
            prd_task_obj.id,
            status="done",
            owner=TaskOwner.PRODUCT_OWNER,
            notes="PRD created",
        )

    try:
        pool.delete(f"pause:{tenant_id}:{purpose_id}")
    except Exception as e:
        logging.error("Failed to remove pause flag: %s", e)
    try:
        ingest(tenant_id)
    except Exception as e:
        logging.error("Failed to ingest graph for tenant %s: %s", tenant_id, e)
    return {"status": "started"}


@router.patch("/{purpose_id}")
def update_purpose(
    purpose_id: str, payload: dict, current_tenant: Tenant = Depends(get_current_tenant)
):
    """Update a Purpose (toggle mode auto/manual)."""
    tenant_id = current_tenant.id
    with Session(engine) as session:
        purpose = session.get(Purpose, purpose_id)
        if not purpose or purpose.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="Purpose not found")
        new_mode = payload.get("mode")
        if new_mode:
            if new_mode not in ("auto", "manual"):
                raise HTTPException(status_code=400, detail="Invalid mode value")
            purpose.mode = new_mode
        session.add(purpose)
        session.commit()
        session.refresh(purpose)
    return {"purpose_id": purpose.id, "mode": purpose.mode}


@router.delete("/{purpose_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_purpose(
    purpose_id: str, current_tenant: Tenant = Depends(get_current_tenant)
) -> Response:
    tenant_id = current_tenant.id
    with Session(engine) as session:
        purpose = session.get(Purpose, purpose_id)
        if not purpose or purpose.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="Purpose not found")

        task_ids = _delete_related_records(session, purpose_id)
        session.delete(purpose)
        session.commit()

    pause_key = f"pause:{tenant_id}:{purpose_id}"
    try:
        pool.delete(pause_key)
    except Exception as exc:  # pragma: no cover - Redis best effort
        logger.warning("Failed to clear pause flag %s: %s", pause_key, exc)

    _cleanup_graph(task_ids, purpose_id)
    _remove_workspace_dir(tenant_id, purpose_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
