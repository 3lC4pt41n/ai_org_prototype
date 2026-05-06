from __future__ import annotations

from typing import Any, Iterable

from ai_org_backend.graph.schema import PipelineEdge, PipelineGraph, PipelineNode
from ai_org_backend.intent.schema import UserIntent


def _field(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _node_kind(agent_role: str | None, slug: str) -> str:
    role = (agent_role or "").lower()
    slug = slug.lower()
    if "review" in role or "review" in slug:
        return "reviewer"
    if "planner" in role or "plan" in slug:
        return "planner"
    if "qa" in role:
        return "evaluator"
    if "repo" in role:
        return "tool"
    return "generator"


def legacy_phases_to_graph(
    *,
    graph_id: str,
    intent: UserIntent,
    phases: Iterable[Any],
    template_family: str | None = "legacy_phases",
) -> PipelineGraph:
    phase_list = sorted(
        list(phases),
        key=lambda phase: int(_field(phase, "position", _field(phase, "order", 0)) or 0),
    )
    nodes: list[PipelineNode] = []
    edges: list[PipelineEdge] = []
    phase_id_by_source: dict[str, str] = {}

    for index, phase in enumerate(phase_list, start=1):
        phase_id = str(_field(phase, "id", "") or _field(phase, "slug", "") or f"phase_{index}")
        slug = str(_field(phase, "slug", "") or _field(phase, "name", phase_id))
        agent_role = _field(phase, "agent_role", None)
        node = PipelineNode(
            id=slug,
            kind=_node_kind(agent_role, slug),  # type: ignore[arg-type]
            capability=str(agent_role or slug),
            retry_policy={"max_attempts": 3, "backoff": "exponential"},
            timeout_s=300,
            requires_human_approval=bool(_field(phase, "requires_approval", False)),
            metadata={
                "legacy_phase_id": phase_id,
                "legacy_name": _field(phase, "name", slug),
                "prompt_template": _field(phase, "prompt_template", None),
                "model_name": _field(phase, "model_name", None),
            },
        )
        nodes.append(node)
        phase_id_by_source[phase_id] = node.id

    for index, phase in enumerate(phase_list):
        source_id = str(_field(phase, "id", "") or _field(phase, "slug", "") or f"phase_{index + 1}")
        node_id = phase_id_by_source[source_id]
        predecessor_id = _field(phase, "predecessor_id", None)
        if predecessor_id and str(predecessor_id) in phase_id_by_source:
            edges.append(
                PipelineEdge(
                    source=phase_id_by_source[str(predecessor_id)],
                    target=node_id,
                    edge_type="control",
                )
            )
        elif index > 0:
            edges.append(
                PipelineEdge(
                    source=nodes[index - 1].id,
                    target=node_id,
                    edge_type="control",
                )
            )

    return PipelineGraph(
        id=graph_id,
        template_family=template_family,
        intent=intent,
        nodes=nodes,
        edges=edges,
        version=2,
    ).with_checksum()


def graph_to_legacy_phase_dicts(graph: PipelineGraph) -> list[dict[str, Any]]:
    return [
        {
            "id": node.metadata.get("legacy_phase_id", node.id),
            "slug": node.id,
            "name": node.metadata.get("legacy_name", node.id.replace("_", " ").title()),
            "position": index,
            "agent_role": node.capability,
            "requires_approval": node.requires_human_approval,
            "prompt_template": node.metadata.get("prompt_template"),
            "model_name": node.metadata.get("model_name"),
        }
        for index, node in enumerate(graph.nodes, start=1)
    ]
