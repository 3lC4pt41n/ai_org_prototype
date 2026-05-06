from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel

from .schema import PipelineGraph, PipelineNode


IssueSeverity = Literal["error", "warning"]
ArtifactExists = Callable[[str], bool]


class GraphValidationIssue(BaseModel):
    code: str
    message: str
    severity: IssueSeverity = "error"
    node_id: str | None = None
    edge: tuple[str, str] | None = None


class GraphValidationResult(BaseModel):
    valid: bool
    issues: list[GraphValidationIssue]


def _is_high_risk_node(graph: PipelineGraph, node: PipelineNode) -> bool:
    return node.metadata.get("risk") == "high" or (
        graph.intent.risk == "high" and node.kind in {"generator", "tool", "repair", "publish"}
    )


def _schema_type(schema: dict) -> str | None:
    if not schema:
        return None
    if "type" in schema:
        return str(schema["type"])
    ref = schema.get("ref")
    return str(ref) if ref else None


def _cycles(graph: PipelineGraph) -> list[list[str]]:
    adjacency: dict[str, list[str]] = defaultdict(list)
    for edge in graph.edges:
        if edge.edge_type in {"control", "feedback"}:
            adjacency[edge.source].append(edge.target)

    found: list[list[str]] = []
    stack: list[str] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visiting:
            idx = stack.index(node_id)
            found.append(stack[idx:] + [node_id])
            return
        if node_id in visited:
            return
        visiting.add(node_id)
        stack.append(node_id)
        for target in adjacency.get(node_id, []):
            visit(target)
        stack.pop()
        visiting.remove(node_id)
        visited.add(node_id)

    for node in graph.nodes:
        visit(node.id)
    return found


def _reachable_nodes(graph: PipelineGraph) -> set[str]:
    node_ids = {node.id for node in graph.nodes}
    incoming = {node_id: 0 for node_id in node_ids}
    adjacency: dict[str, list[str]] = defaultdict(list)
    for edge in graph.edges:
        if edge.source in node_ids and edge.target in node_ids and edge.edge_type != "invalidates":
            incoming[edge.target] += 1
            adjacency[edge.source].append(edge.target)
    roots = [node_id for node_id, count in incoming.items() if count == 0]
    if not roots and graph.nodes:
        roots = [graph.nodes[0].id]

    reachable: set[str] = set()
    queue = deque(roots)
    while queue:
        node_id = queue.popleft()
        if node_id in reachable:
            continue
        reachable.add(node_id)
        queue.extend(adjacency.get(node_id, []))
    return reachable


def validate_graph(
    graph: PipelineGraph,
    artifact_exists: ArtifactExists | None = None,
) -> GraphValidationResult:
    issues: list[GraphValidationIssue] = []
    node_by_id = {node.id: node for node in graph.nodes}

    if len(node_by_id) != len(graph.nodes):
        issues.append(GraphValidationIssue(code="duplicate_node_id", message="Node IDs must be unique."))
    if not graph.nodes:
        issues.append(GraphValidationIssue(code="empty_graph", message="Graph must contain nodes."))

    for edge in graph.edges:
        if edge.source not in node_by_id or edge.target not in node_by_id:
            issues.append(
                GraphValidationIssue(
                    code="missing_edge_endpoint",
                    message="Every edge endpoint must reference an existing node.",
                    edge=(edge.source, edge.target),
                )
            )
            continue
        if edge.edge_type == "data":
            source_type = _schema_type(node_by_id[edge.source].output_schema)
            target_type = _schema_type(node_by_id[edge.target].input_schema)
            if source_type and target_type and source_type != target_type:
                issues.append(
                    GraphValidationIssue(
                        code="type_incompatible_edge",
                        message=f"Data edge type mismatch: {source_type} -> {target_type}.",
                        edge=(edge.source, edge.target),
                    )
                )

    reachable = _reachable_nodes(graph)
    for node in graph.nodes:
        if node.id not in reachable:
            issues.append(
                GraphValidationIssue(
                    code="dead_node",
                    message="Node is not reachable from any graph root.",
                    node_id=node.id,
                )
            )
        if _is_high_risk_node(graph, node) and not node.requires_human_approval:
            issues.append(
                GraphValidationIssue(
                    code="high_risk_without_approval",
                    message="High-risk execution nodes require human approval.",
                    node_id=node.id,
                )
            )

    for cycle in _cycles(graph):
        bounded = any(
            node_by_id[node_id].max_revisions > 0
            and node_by_id[node_id].cost_budget
            and node_by_id[node_id].metadata.get("convergence_predicate")
            for node_id in cycle
            if node_id in node_by_id
        )
        if not bounded:
            issues.append(
                GraphValidationIssue(
                    code="unbounded_cycle",
                    message="Cycles require max_revisions, cost_budget, and convergence_predicate.",
                )
            )

    if graph.intent.target_artifact_id and artifact_exists is not None:
        if not artifact_exists(graph.intent.target_artifact_id):
            issues.append(
                GraphValidationIssue(
                    code="unresolved_artifact_reference",
                    message="Graph intent references an artifact that cannot be resolved.",
                )
            )

    return GraphValidationResult(
        valid=not any(issue.severity == "error" for issue in issues),
        issues=issues,
    )
