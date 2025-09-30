import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import and_, update
from sqlmodel import Session, select

from ai_org_backend.api.dependencies import get_current_tenant
from ai_org_backend.db import engine
from ai_org_backend.models import Artifact, Purpose, Task, TaskOwner, Tenant
from ai_org_backend.redis_client import pool
from ai_org_backend.repo import Repo
from ai_org_backend.scripts.seed_graph import ingest
from ai_org_backend.services import graph_sync
from ai_org_backend.services.storage import register_artefact, retract_artifact
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

        # collect related tasks and artifacts before deletion
        task_ids = session.exec(
            select(Task.id).where(
                Task.tenant_id == tenant_id,
                Task.purpose_id == purpose_id,
            )
        ).all()
        artifact_ids = session.exec(
            select(Artifact.id).where(
                Artifact.task.has(
                    and_(Task.purpose_id == purpose_id, Task.tenant_id == tenant_id)
                )
            )
        ).all()

        # retract artifacts from vector store / graph (best-effort)
        for artifact_id in artifact_ids:
            try:
                retract_artifact(artifact_id, remove_from_neo4j=True)
            except Exception as exc:  # pragma: no cover - cleanup best effort
                logging.error(
                    "Failed to retract artifact %s for purpose %s: %s",
                    artifact_id,
                    purpose_id,
                    exc,
                )

        # delete tasks and purpose from SQL
        if task_ids:
            for task in session.exec(
                select(Task).where(Task.id.in_(task_ids))
            ).all():
                session.delete(task)
        session.delete(purpose)
        session.commit()

    # cleanup redis keys (best-effort)
    try:
        if pool is not None:
            pool.delete(f"pause:{tenant_id}:{purpose_id}")
            pool.delete(f"budget:{tenant_id}:{purpose_id}")
    except Exception as exc:  # pragma: no cover - cache cleanup best effort
        logging.error(
            "Failed to remove redis keys for purpose %s (tenant %s): %s",
            purpose_id,
            tenant_id,
            exc,
        )

    # remove nodes from graph database (best-effort)
    try:
        graph_sync.remove_tasks(task_ids)
        graph_sync.remove_purpose(purpose_id)
    except Exception as exc:  # pragma: no cover - best effort cleanup
        logging.error(
            "Failed to remove tasks or purpose from graph for %s: %s",
            purpose_id,
            exc,
        )

    # safe workspace cleanup (best effort)
    try:
        root = Path(settings.workspace_dir).resolve()
        candidate = (root / tenant_id / purpose_id).resolve()
        candidate.relative_to(root)
    except ValueError:
        pass
    except Exception as exc:  # pragma: no cover
        logging.error("Failed to resolve workspace for purpose %s: %s", purpose_id, exc)
    else:
        try:
            shutil.rmtree(candidate, ignore_errors=True)
        except Exception as exc:  # pragma: no cover
            logging.error("Failed to remove workspace for purpose %s: %s", purpose_id, exc)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
