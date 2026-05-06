from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from ai_org_backend.graph.schema import PipelineEdge, PipelineGraph, PipelineNode
from ai_org_backend.graph.template_matcher import best_template, instantiate_template
from ai_org_backend.graph.validator import validate_graph
from ai_org_backend.intent.schema import UserIntent


CATALOG_DIR = Path(__file__).resolve().parent / "capability_catalog"
MAX_SYNTH_NODES = 20
MAX_SYNTH_LOOPS = 3


class GraphSynthesisError(RuntimeError):
    pass


class Capability(BaseModel):
    id: str
    domain: str
    actions: list[str]
    deliverable_types: list[str]
    node_kind: str
    cost_eur: float = 0.0
    risk: str = "medium"


def load_capabilities(catalog_dir: Path = CATALOG_DIR) -> list[Capability]:
    capabilities: list[Capability] = []
    if not catalog_dir.exists():
        return capabilities
    for path in sorted(catalog_dir.glob("*.yaml")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        capabilities.append(Capability(**payload))
    return capabilities


def _matches(capability: Capability, intent: UserIntent) -> bool:
    return (
        capability.domain in {intent.domain, "general"}
        and ("*" in capability.actions or intent.action in capability.actions)
        and ("*" in capability.deliverable_types or intent.deliverable_type in capability.deliverable_types)
    )


def _pick(capabilities: list[Capability], kind: str) -> Capability | None:
    for capability in capabilities:
        if capability.node_kind == kind:
            return capability
    return None


def _budget_limit(intent: UserIntent) -> float | None:
    budget = intent.constraints.get("budget")
    if isinstance(budget, dict) and budget.get("cost_eur") is not None:
        return float(budget["cost_eur"])
    if intent.constraints.get("budget_eur") is not None:
        return float(intent.constraints["budget_eur"])
    return None


def synthesize_graph_from_capabilities(
    intent: UserIntent,
    catalog: list[Capability] | None = None,
) -> PipelineGraph:
    catalog = catalog or load_capabilities()
    matching = [capability for capability in catalog if _matches(capability, intent)]
    if not matching:
        raise GraphSynthesisError("No declared capability matches the intent.")

    ordered: list[Capability] = []
    for kind in ("planner", "tool", "generator", "evaluator", "publish"):
        capability = _pick(matching, kind)
        if capability and capability not in ordered:
            ordered.append(capability)
    if not ordered:
        raise GraphSynthesisError("Matching capabilities do not contain executable node kinds.")

    total_cost = round(sum(capability.cost_eur for capability in ordered), 6)
    budget_limit = _budget_limit(intent)
    if budget_limit is not None and total_cost > budget_limit:
        raise GraphSynthesisError(
            f"Estimated cost {total_cost} EUR exceeds budget {budget_limit} EUR."
        )

    constraints = dict(intent.constraints)
    constraints["graph.origin"] = "synthesized"
    constraints["estimated_cost_eur"] = total_cost
    graph_intent = intent.model_copy(update={"constraints": constraints})

    nodes: list[PipelineNode] = []
    for idx, capability in enumerate(ordered, start=1):
        requires_approval = intent.risk == "high" or capability.risk == "high"
        nodes.append(
            PipelineNode(
                id=f"n{idx}_{capability.id.replace('.', '_')}",
                kind=capability.node_kind,  # type: ignore[arg-type]
                capability=capability.id,
                requires_human_approval=requires_approval,
                cost_budget={"cost_eur": capability.cost_eur} if capability.cost_eur else None,
                metadata={"risk": capability.risk},
            )
        )
    if intent.risk == "high":
        nodes.append(
            PipelineNode(
                id="human_approval",
                kind="approval",
                capability="human.approval",
                requires_human_approval=True,
                metadata={"risk": "high"},
            )
        )

    if len(nodes) > MAX_SYNTH_NODES:
        raise GraphSynthesisError("Synthesized graph exceeds the 20-node limit.")

    edges = [
        PipelineEdge(source=nodes[idx].id, target=nodes[idx + 1].id)
        for idx in range(len(nodes) - 1)
    ]
    graph = PipelineGraph(
        id=f"synthesized.{intent.domain}.{intent.action}.{intent.deliverable_type}",
        template_family=None,
        intent=graph_intent,
        nodes=nodes,
        edges=edges,
        version=1,
    ).with_checksum()
    validation = validate_graph(graph)
    if not validation.valid:
        raise GraphSynthesisError(f"Synthesized invalid graph: {validation.model_dump()}")
    return graph


def compile_graph(intent: UserIntent, catalog: list[Capability] | None = None) -> PipelineGraph:
    candidate = best_template(intent, min_confidence=0.75)
    if candidate and intent.confidence >= 0.75:
        return instantiate_template(intent, candidate)
    return synthesize_graph_from_capabilities(intent, catalog)
