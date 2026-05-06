from __future__ import annotations

from sqlmodel import Session, delete, select

from ai_org_backend.graph.persistence import graph_from_record_payloads, graph_to_record_payloads
from ai_org_backend.graph.schema import PipelineGraph
from ai_org_backend.graph.synthesizer import compile_graph
from ai_org_backend.graph.workflow_search import WorkflowSearchLimits, bounded_workflow_search
from ai_org_backend.intent.schema import UserIntent
from ai_org_backend.models import PipelineEdgeRecord, PipelineGraphRecord, PipelineNodeRecord


def compile_pipeline_graph(
    intent: UserIntent,
    *,
    use_workflow_search: bool = False,
) -> PipelineGraph:
    if use_workflow_search:
        result = bounded_workflow_search(intent, WorkflowSearchLimits())
        if result.selected_graph is None:
            raise ValueError(result.rejected_reason or "workflow search rejected all candidates")
        return result.selected_graph
    return compile_graph(intent)


def save_pipeline_graph(
    session: Session,
    graph: PipelineGraph,
    *,
    tenant_id: str | None = None,
    purpose_id: str | None = None,
) -> PipelineGraphRecord:
    payloads = graph_to_record_payloads(graph)
    graph_payload = payloads["graph"]
    graph_payload["tenant_id"] = tenant_id
    graph_payload["purpose_id"] = purpose_id
    session.exec(delete(PipelineEdgeRecord).where(PipelineEdgeRecord.graph_id == graph.id))
    session.exec(delete(PipelineNodeRecord).where(PipelineNodeRecord.graph_id == graph.id))
    existing = session.get(PipelineGraphRecord, graph.id)
    if existing:
        session.delete(existing)
        session.flush()
    graph_record = PipelineGraphRecord(**graph_payload)
    session.add(graph_record)
    session.flush()
    for node_payload in payloads["nodes"]:
        session.add(PipelineNodeRecord(**node_payload))
    for edge_payload in payloads["edges"]:
        session.add(PipelineEdgeRecord(**edge_payload))
    session.commit()
    session.refresh(graph_record)
    return graph_record


def load_pipeline_graph(
    session: Session,
    graph_id: str,
    *,
    tenant_id: str | None = None,
) -> PipelineGraph | None:
    graph_record = session.get(PipelineGraphRecord, graph_id)
    if graph_record is None:
        return None
    if tenant_id is not None and graph_record.tenant_id != tenant_id:
        return None
    nodes = session.exec(select(PipelineNodeRecord).where(PipelineNodeRecord.graph_id == graph_id)).all()
    edges = session.exec(select(PipelineEdgeRecord).where(PipelineEdgeRecord.graph_id == graph_id)).all()
    return graph_from_record_payloads(
        graph_record.model_dump(mode="json"),
        [node.model_dump(mode="json") for node in nodes],
        [edge.model_dump(mode="json") for edge in edges],
    )


def load_latest_pipeline_graph_for_purpose(
    session: Session,
    purpose_id: str,
    *,
    tenant_id: str | None = None,
) -> PipelineGraph | None:
    statement = select(PipelineGraphRecord).where(PipelineGraphRecord.purpose_id == purpose_id)
    if tenant_id is not None:
        statement = statement.where(PipelineGraphRecord.tenant_id == tenant_id)
    graph_record = session.exec(
        statement.order_by(
            PipelineGraphRecord.created_at.desc(),
            PipelineGraphRecord.id.desc(),
        )
    ).first()
    if graph_record is None:
        return None
    return load_pipeline_graph(session, graph_record.id, tenant_id=tenant_id)
