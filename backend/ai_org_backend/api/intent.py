"""Intent compiler endpoints for UI review and correction."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlmodel import Session

from ai_org_backend.api.dependencies import get_current_tenant, get_session
from ai_org_backend.intent import CompiledIntent, IntentCompiler, legacy_role_for_intent
from ai_org_backend.intent.schema import UserIntent
from ai_org_backend.intent.validator import validate_intent
from ai_org_backend.models import Artifact, Task, Tenant

router = APIRouter(prefix="/api/intent", tags=["intent"])


class IntentCompileRequest(BaseModel):
    raw_request: str = Field(min_length=1)


class IntentValidateRequest(BaseModel):
    intent: UserIntent


class IntentValidationResponse(BaseModel):
    intent: UserIntent
    validation: dict[str, Any]
    legacy_role: str
    requires_clarification: bool
    clarification_reason: str | None = None


def _artifact_type(artifact: Artifact) -> str:
    repo_path = (artifact.repo_path or "").lower()
    media_type = (artifact.media_type or "").lower()
    if "architecture" in repo_path or "blueprint" in repo_path:
        return "architecture_blueprint"
    if "implementation" in repo_path or "plan" in repo_path:
        return "implementation_plan"
    if "prd" in repo_path or "requirement" in repo_path:
        return "prd"
    if media_type.startswith("text/"):
        return "document"
    return "artifact"


def _compiler_for_tenant(session: Session, tenant_id: str) -> IntentCompiler:
    def lookup(artifact_id: str) -> dict[str, Any] | None:
        artifact = session.get(Artifact, artifact_id)
        if artifact is None:
            return None
        task = session.get(Task, artifact.task_id)
        if task is None or task.tenant_id != tenant_id:
            return None
        return {
            "type": _artifact_type(artifact),
            "version_id": f"{artifact.id}:v{artifact.version_number}",
        }

    return IntentCompiler(artifact_lookup=lookup)


@router.post("/compile", response_model=CompiledIntent)
def compile_intent_endpoint(
    request: IntentCompileRequest,
    current_tenant: Tenant = Depends(get_current_tenant),
    session: Session = Depends(get_session),
) -> CompiledIntent:
    """Compile a raw user request into a structured multi-axis intent."""

    compiler = _compiler_for_tenant(session, current_tenant.id)
    return compiler.compile(request.raw_request)


@router.post("/validate", response_model=IntentValidationResponse)
def validate_intent_endpoint(
    request: IntentValidateRequest,
    current_tenant: Tenant = Depends(get_current_tenant),
) -> IntentValidationResponse:
    """Validate a user-edited intent before graph or legacy routing."""

    validation = validate_intent(request.intent)
    clarification_reason = None
    if validation.needs_clarification:
        clarification_reason = "; ".join(issue.message for issue in validation.issues)
    return IntentValidationResponse(
        intent=request.intent,
        validation=validation.model_dump(),
        legacy_role=legacy_role_for_intent(request.intent),
        requires_clarification=validation.needs_clarification,
        clarification_reason=clarification_reason,
    )
