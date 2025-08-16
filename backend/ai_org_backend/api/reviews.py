from ai_org_backend.api.dependencies import get_current_tenant
from ai_org_backend.db import engine
from ai_org_backend.models import Task, Tenant
from ai_org_backend.repo import Repo
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

"""Endpoints for approving Architecture & Domain Review tasks."""

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.get("/{task_id}")
def get_review(task_id: str, current_tenant: Tenant = Depends(get_current_tenant)):
    with Session(engine) as s:
        t = s.get(Task, task_id)
        if not t:
            raise HTTPException(status_code=404, detail="Task not found")
        if t.tenant_id != current_tenant.id:
            raise HTTPException(status_code=403, detail="Forbidden for this tenant")
        return {
            "id": t.id,
            "description": t.description,
            "status": str(t.status),
            "owner": t.owner,
            "notes": t.notes,
        }


@router.post("/{task_id}/approve")
def approve_review(task_id: str, current_tenant: Tenant = Depends(get_current_tenant)):
    """
    Mark the review as done; keeps owner 'Review'. Downstream tasks will be unblocked
    by the dependency DAG (no extra logic required here).
    """
    with Session(engine) as s:
        t = s.get(Task, task_id)
        if not t:
            raise HTTPException(status_code=404, detail="Task not found")
        if t.tenant_id != current_tenant.id:
            raise HTTPException(status_code=403, detail="Forbidden for this tenant")
        if t.description.lower() != "architecture & domain review":
            raise HTTPException(status_code=400, detail="Not a review task")
        Repo(current_tenant.id).update(task_id, status="done", owner="Review", notes="approved")
        return {"ok": True, "task_id": task_id, "status": "done"}
