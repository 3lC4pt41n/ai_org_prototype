from __future__ import annotations

from typing import Any

from ai_org_backend.graph.schema import PipelineEdge, PipelineGraph, PipelineNode
from ai_org_backend.intent.schema import UserIntent


def graph_to_record_payloads(graph: PipelineGraph) -> dict[str, Any]:
    checked = graph.with_checksum()
    return {
        "graph": {
            "id": checked.id,
            "template_family": checked.template_family,
            "intent_json": checked.intent.model_dump(mode="json"),
            "version": checked.version,
            "checksum": checked.checksum,
        },
        "nodes": [
            {
                "id": node.id,
                "graph_id": checked.id,
                "kind": node.kind,
                "capability": node.capability,
                "input_schema_json": node.input_schema,
                "output_schema_json": node.output_schema,
                "retry_policy_json": node.retry_policy,
                "timeout_s": node.timeout_s,
                "max_revisions": node.max_revisions,
                "requires_human_approval": node.requires_human_approval,
                "cost_budget_json": node.cost_budget,
                "metadata_json": node.metadata,
            }
            for node in checked.nodes
        ],
        "edges": [
            {
                "graph_id": checked.id,
                "source": edge.source,
                "target": edge.target,
                "condition": edge.condition,
                "activation": edge.activation,
                "edge_type": edge.edge_type,
            }
            for edge in checked.edges
        ],
    }


def graph_from_record_payloads(
    graph_payload: dict[str, Any],
    node_payloads: list[dict[str, Any]],
    edge_payloads: list[dict[str, Any]],
) -> PipelineGraph:
    graph = PipelineGraph(
        id=graph_payload["id"],
        template_family=graph_payload.get("template_family"),
        intent=UserIntent.model_validate(graph_payload["intent_json"]),
        nodes=[
            PipelineNode(
                id=node["id"],
                kind=node["kind"],
                capability=node["capability"],
                input_schema=node.get("input_schema_json") or {},
                output_schema=node.get("output_schema_json") or {},
                retry_policy=node.get("retry_policy_json") or {},
                timeout_s=node.get("timeout_s") or 300,
                max_revisions=node.get("max_revisions") or 0,
                requires_human_approval=bool(node.get("requires_human_approval")),
                cost_budget=node.get("cost_budget_json"),
                metadata=node.get("metadata_json") or {},
            )
            for node in node_payloads
        ],
        edges=[
            PipelineEdge(
                source=edge["source"],
                target=edge["target"],
                condition=edge.get("condition"),
                activation=edge.get("activation", "all"),
                edge_type=edge.get("edge_type", "control"),
            )
            for edge in edge_payloads
        ],
        version=graph_payload.get("version", 1),
        checksum=graph_payload.get("checksum", ""),
    )
    return graph.with_checksum()
