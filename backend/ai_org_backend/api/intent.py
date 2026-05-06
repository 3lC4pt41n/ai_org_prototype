"""Intent compiler endpoints for UI review and correction."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session

from ai_org_backend.api.dependencies import get_current_tenant, get_session
from ai_org_backend.intent import CompiledIntent, IntentCompiler, legacy_role_for_intent
from ai_org_backend.intent.schema import UserIntent
from ai_org_backend.intent.validator import validate_intent
from ai_org_backend.models import Artifact, IntentReview, Purpose, Task, Tenant

router = APIRouter(prefix="/api/intent", tags=["intent"])


class IntentCompileRequest(BaseModel):
    raw_request: str = Field(min_length=1)
    use_llm_fallback: bool = False
    purpose_id: str | None = None


class IntentValidateRequest(BaseModel):
    intent: UserIntent


class IntentValidationResponse(BaseModel):
    intent: UserIntent
    validation: dict[str, Any]
    legacy_role: str
    requires_clarification: bool
    clarification_reason: str | None = None


class IntentReviewResponse(BaseModel):
    id: str
    tenant_id: str
    purpose_id: str | None = None
    raw_request: str
    intent: UserIntent
    validation: dict[str, Any]
    legacy_role: str
    requires_clarification: bool
    clarification_reason: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime | None = None


class IntentReviewUpdateRequest(BaseModel):
    intent: UserIntent | None = None
    status: str | None = Field(default=None, pattern="^(draft|validated|approved|superseded)$")


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


def _compiler_for_tenant(
    session: Session,
    tenant_id: str,
    *,
    use_llm_fallback: bool = False,
) -> IntentCompiler:
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

    return IntentCompiler(
        artifact_lookup=lookup,
        use_llm_fallback=use_llm_fallback,
        tenant_id=tenant_id,
    )


def _review_response(review: IntentReview) -> IntentReviewResponse:
    return IntentReviewResponse(
        id=review.id,
        tenant_id=review.tenant_id,
        purpose_id=review.purpose_id,
        raw_request=review.raw_request,
        intent=UserIntent.model_validate(review.intent_json),
        validation=review.validation_json,
        legacy_role=review.legacy_role,
        requires_clarification=review.requires_clarification,
        clarification_reason=review.clarification_reason,
        status=review.status,
        created_at=review.created_at,
        updated_at=review.updated_at,
    )


def _load_review(session: Session, review_id: str, tenant_id: str) -> IntentReview:
    review = session.get(IntentReview, review_id)
    if review is None or review.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Intent review not found")
    return review


def _ensure_purpose_access(session: Session, purpose_id: str | None, tenant_id: str) -> None:
    if purpose_id is None:
        return
    purpose = session.get(Purpose, purpose_id)
    if purpose is None or purpose.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Purpose not found")


@router.post("/compile", response_model=CompiledIntent)
def compile_intent_endpoint(
    request: IntentCompileRequest,
    current_tenant: Tenant = Depends(get_current_tenant),
    session: Session = Depends(get_session),
) -> CompiledIntent:
    """Compile a raw user request into a structured multi-axis intent."""

    compiler = _compiler_for_tenant(
        session,
        current_tenant.id,
        use_llm_fallback=request.use_llm_fallback,
    )
    return compiler.compile(request.raw_request)


@router.post("/reviews", response_model=IntentReviewResponse, status_code=201)
def create_intent_review_endpoint(
    request: IntentCompileRequest,
    current_tenant: Tenant = Depends(get_current_tenant),
    session: Session = Depends(get_session),
) -> IntentReviewResponse:
    """Compile and persist an intent draft for UI review before execution."""

    _ensure_purpose_access(session, request.purpose_id, current_tenant.id)
    compiler = _compiler_for_tenant(
        session,
        current_tenant.id,
        use_llm_fallback=request.use_llm_fallback,
    )
    compiled = compiler.compile(request.raw_request)
    review = IntentReview(
        tenant_id=current_tenant.id,
        purpose_id=request.purpose_id,
        raw_request=request.raw_request,
        intent_json=compiled.intent.model_dump(),
        validation_json=compiled.validation.model_dump(),
        legacy_role=compiled.legacy_role,
        requires_clarification=compiled.requires_clarification,
        clarification_reason=compiled.clarification_reason,
        status="draft" if compiled.requires_clarification else "validated",
    )
    session.add(review)
    session.commit()
    session.refresh(review)
    return _review_response(review)


@router.get("/reviews/{review_id}", response_model=IntentReviewResponse)
def get_intent_review_endpoint(
    review_id: str,
    current_tenant: Tenant = Depends(get_current_tenant),
    session: Session = Depends(get_session),
) -> IntentReviewResponse:
    """Read a persisted intent draft for UI display."""

    return _review_response(_load_review(session, review_id, current_tenant.id))


@router.patch("/reviews/{review_id}", response_model=IntentReviewResponse)
def update_intent_review_endpoint(
    review_id: str,
    request: IntentReviewUpdateRequest,
    current_tenant: Tenant = Depends(get_current_tenant),
    session: Session = Depends(get_session),
) -> IntentReviewResponse:
    """Edit and revalidate a persisted intent draft before execution."""

    review = _load_review(session, review_id, current_tenant.id)
    if request.intent is not None:
        validation = validate_intent(request.intent)
        clarification_reason = None
        if validation.needs_clarification:
            clarification_reason = "; ".join(issue.message for issue in validation.issues)
        review.intent_json = request.intent.model_dump()
        review.validation_json = validation.model_dump()
        review.legacy_role = legacy_role_for_intent(request.intent)
        review.requires_clarification = validation.needs_clarification
        review.clarification_reason = clarification_reason
        review.status = "draft" if validation.needs_clarification else "validated"
    if request.status is not None:
        if request.status == "approved" and review.requires_clarification:
            raise HTTPException(
                status_code=409,
                detail="Cannot approve an intent that still requires clarification",
            )
        review.status = request.status
    review.updated_at = datetime.utcnow()
    session.add(review)
    session.commit()
    session.refresh(review)
    return _review_response(review)


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
