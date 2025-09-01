from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ai_org_backend.api.dependencies import get_current_tenant
from ai_org_backend.db import engine
from ai_org_backend.models import Artifact, ArtifactFeedback, Task, Tenant

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


@router.post("/{artifact_id}")
def post_feedback(
    artifact_id: str,
    payload: dict,
    current_tenant: Tenant = Depends(get_current_tenant),
):
    tenant_id = current_tenant.id
    text = (payload.get("content") or payload.get("feedback") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Feedback content required")

    with Session(engine) as session:
        artifact = session.get(Artifact, artifact_id)
        if not artifact:
            raise HTTPException(status_code=404, detail="Artifact not found")
        task = session.get(Task, artifact.task_id)
        if not task or task.tenant_id != tenant_id:
            raise HTTPException(status_code=403, detail="Forbidden for this tenant")

        last_version = session.exec(
            select(ArtifactFeedback.version)
            .where(ArtifactFeedback.artifact_id == artifact_id)
            .order_by(ArtifactFeedback.version.desc())
        ).first()
        version = (last_version or 0) + 1
        fb = ArtifactFeedback(
            artifact_id=artifact_id,
            tenant_id=tenant_id,
            version=version,
            content=text,
            approved=False,
        )
        session.add(fb)
        session.commit()
    return {"status": "saved", "version": version}
