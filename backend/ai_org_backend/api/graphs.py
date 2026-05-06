from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from ai_org_backend.api.dependencies import get_current_tenant, get_session
from ai_org_backend.intent import IntentCompiler
from ai_org_backend.intent.schema import UserIntent
from ai_org_backend.models import IntentReview, Purpose, Tenant
from ai_org_backend.services.graph_compiler import (
    compile_pipeline_graph,
    load_latest_pipeline_graph_for_purpose,
    load_pipeline_graph,
    save_pipeline_graph,
)

router = APIRouter(prefix="/api/graphs", tags=["graphs"])


class GraphCompileRequest(BaseModel):
    intent_review_id: str | None = None
    raw_request: str | None = None
    intent: UserIntent | None = None
    persist: bool = True
    use_workflow_search: bool = False


class GraphCompileResponse(BaseModel):
    graph: dict[str, Any]
    persisted: bool


class PurposeGraphResponse(BaseModel):
    graph: dict[str, Any] | None = None


def _intent_from_request(
    request: GraphCompileRequest,
    *,
    session: Session,
    tenant_id: str,
) -> UserIntent:
    if request.intent is not None:
        return request.intent
    if request.intent_review_id:
        review = session.get(IntentReview, request.intent_review_id)
        if review is None or review.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="Intent review not found")
        if review.requires_clarification or review.status not in {"validated", "approved"}:
            raise HTTPException(status_code=409, detail="Intent review must be validated before graph compile")
        return UserIntent.model_validate(review.intent_json)
    if request.raw_request:
        compiled = IntentCompiler(tenant_id=tenant_id).compile(request.raw_request)
        if compiled.requires_clarification:
            raise HTTPException(status_code=409, detail=compiled.clarification_reason)
        return compiled.intent
    raise HTTPException(status_code=400, detail="Provide intent, intent_review_id, or raw_request")


@router.post("/compile", response_model=GraphCompileResponse)
def compile_graph_endpoint(
    request: GraphCompileRequest,
    current_tenant: Tenant = Depends(get_current_tenant),
    session: Session = Depends(get_session),
) -> GraphCompileResponse:
    """Compile a validated intent into a PipelineGraph and optionally persist it."""

    intent = _intent_from_request(request, session=session, tenant_id=current_tenant.id)
    graph = compile_pipeline_graph(intent, use_workflow_search=request.use_workflow_search)
    if request.persist:
        save_pipeline_graph(session, graph, tenant_id=current_tenant.id)
    return GraphCompileResponse(graph=graph.model_dump(mode="json"), persisted=request.persist)


@router.get("/purpose/{purpose_id}", response_model=PurposeGraphResponse)
def get_latest_graph_for_purpose_endpoint(
    purpose_id: str,
    current_tenant: Tenant = Depends(get_current_tenant),
    session: Session = Depends(get_session),
) -> PurposeGraphResponse:
    """Read the latest persisted PipelineGraph for a purpose."""

    purpose = session.get(Purpose, purpose_id)
    if purpose is None or purpose.tenant_id != current_tenant.id:
        raise HTTPException(status_code=404, detail="Purpose not found")
    graph = load_latest_pipeline_graph_for_purpose(
        session,
        purpose_id,
        tenant_id=current_tenant.id,
    )
    return PurposeGraphResponse(
        graph=graph.model_dump(mode="json") if graph is not None else None,
    )


@router.get("/{graph_id}")
def get_graph_endpoint(
    graph_id: str,
    current_tenant: Tenant = Depends(get_current_tenant),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Read a persisted PipelineGraph."""

    graph = load_pipeline_graph(session, graph_id, tenant_id=current_tenant.id)
    if graph is None:
        raise HTTPException(status_code=404, detail="Graph not found")
    return graph.model_dump(mode="json")
