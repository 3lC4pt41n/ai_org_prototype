import os
from pathlib import Path

from ai_org_backend.db import engine
from ai_org_backend.models import Artifact, Task
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from ..services import budget
from .dependencies import get_current_tenant

router = APIRouter()


@router.get("/")
def root():
    """Public health endpoint with budget info for default tenant."""
    tid = os.getenv("DEFAULT_TENANT", "demo")
    return {
        "status": "alive",
        "budget_left": budget.get_left(tid),
        "budget_total": budget.get_total(tid),
    }


@router.get("/artifacts")
async def list_artifacts(current_tenant=Depends(get_current_tenant)):
    """List PM agent artifacts (standups, plan adjustments) for the current tenant."""
    with Session(engine) as session:
        results = session.exec(
            select(Artifact)
            .join(Task)
            .where(Task.tenant_id == current_tenant.id, Task.owner == "PM")
            .order_by(Artifact.created_at.desc())
        ).all()
    return [
        {
            "id": art.id,
            "name": art.repo_path.split("/", 1)[1] if "/" in art.repo_path else art.repo_path,
            "created_at": art.created_at.isoformat(),
        }
        for art in results
    ]


@router.get("/artifact/{artifact_id}")
async def download_artifact(artifact_id: str, current_tenant=Depends(get_current_tenant)):
    """Download the content of a given artifact file."""
    with Session(engine) as session:
        art = session.get(Artifact, artifact_id)
        if not art or art.task.tenant_id != current_tenant.id:
            raise HTTPException(status_code=404, detail="Artifact not found")
    file_path = (Path.cwd() / "workspace") / art.repo_path
    if not file_path.exists():
        raise HTTPException(status_code=410, detail="File not available")
    return FileResponse(file_path, media_type=art.media_type, filename=file_path.name)
