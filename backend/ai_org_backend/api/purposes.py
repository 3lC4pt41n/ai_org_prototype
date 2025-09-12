from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import update
from sqlmodel import Session, select

from ai_org_backend.api.dependencies import get_current_tenant
from ai_org_backend.db import engine
from ai_org_backend.models import Artifact, Purpose, Task, Tenant
from ai_org_backend.redis_client import pool
from ai_org_backend.repo import Repo
from ai_org_backend.scripts.seed_graph import ingest
from ai_org_backend.services.storage import save_artefact

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
    except Exception:
        pass
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
            except Exception:
                pass
            return {"status": "resumed", "idempotent": True}

        prd_task_obj = Task(
            tenant_id=tenant_id,
            purpose_id=purpose_id,
            description="Product Requirements Document",
            status="done",
            owner="Product Owner",
        )
        session.add(prd_task_obj)
        session.commit()
        session.refresh(prd_task_obj)

        prd_md = (
            f"# Product Requirements Document\n\n"
            f"**Purpose:** {purpose.name}\n\n"
            f"## Overview\n\nTBD\n"
        )
        save_artefact(
            prd_task_obj.id,
            prd_md.encode("utf-8"),
            filename="requirements/product_requirements_document.md",
            media_type="text/markdown",
            allow_overwrite=True,
        )
        Repo(tenant_id).update(
            prd_task_obj.id, status="done", owner="Product Owner", notes="PRD created"
        )

    try:
        pool.delete(f"pause:{tenant_id}:{purpose_id}")
    except Exception:
        pass
    try:
        ingest(tenant_id)
    except Exception:
        pass
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
