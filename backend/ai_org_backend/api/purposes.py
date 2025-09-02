from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import update
from sqlmodel import Session, select

from ai_org_backend.api.dependencies import get_current_tenant
from ai_org_backend.db import engine
from ai_org_backend.models import Purpose, Task, Tenant
from ai_org_backend.repo import Repo
from ai_org_backend.services.storage import save_artefact

router = APIRouter(prefix="/api/purposes", tags=["purposes"])


@router.post("/{purpose_id}/activate")
def activate_purpose(purpose_id: str, current_tenant: Tenant = Depends(get_current_tenant)):
    tenant_id = current_tenant.id
    with Session(engine) as session:
        session.exec(
            update(Purpose).where(Purpose.tenant_id == tenant_id).values(is_active=False)
        )
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
        purpose.is_active = False
        session.add(purpose)
        session.commit()
    return {"status": "paused", "purpose_id": purpose_id}


@router.post("/{purpose_id}/start")
def start_purpose(purpose_id: str, current_tenant: Tenant = Depends(get_current_tenant)):
    tenant_id = current_tenant.id
    with Session(engine) as session:
        purpose = session.get(Purpose, purpose_id)
        if not purpose or purpose.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="Purpose not found")

        existing = session.exec(
            select(Task)
            .where(
                Task.tenant_id == tenant_id,
                Task.purpose_id == purpose_id,
                Task.description.like("Product Requirements Document%"),
            )
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="PRD already exists")

    try:
        from ai_org_backend.agents.product_owner import run_requirements

        prd_content = run_requirements(purpose)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Requirements gathering failed: {e}")

    with Session(engine) as session:
        prd_task = Task(
            tenant_id=tenant_id,
            purpose_id=purpose_id,
            description="Product Requirements Document",
            business_value=0.0,
            tokens_plan=0,
            purpose_relevance=1.0,
        )
        session.add(prd_task)
        session.commit()
        session.refresh(prd_task)

    save_artefact(
        prd_task.id,
        prd_content.encode("utf-8"),
        filename="requirements/product_requirements.md",
        media_type="text/markdown",
    )
    Repo(tenant_id).update(
        prd_task.id, status="done", owner="ProductOwner", notes="PRD completed"
    )
    return {"status": "started", "purpose_id": purpose_id}
