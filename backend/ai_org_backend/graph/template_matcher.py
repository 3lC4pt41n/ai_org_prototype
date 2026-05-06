from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_org_backend.graph.schema import PipelineEdge, PipelineGraph, PipelineNode
from ai_org_backend.graph.validator import validate_graph
from ai_org_backend.intent.schema import UserIntent


TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


@dataclass(frozen=True)
class TemplateCandidate:
    template_id: str
    family: str
    confidence: float
    path: Path
    template: dict[str, Any]


def load_template_file(path: Path) -> dict[str, Any]:
    """Load a JSON-compatible YAML template without adding a YAML dependency."""

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Template {path} must contain an object")
    return data


def load_templates(template_dir: Path = TEMPLATE_DIR) -> list[dict[str, Any]]:
    if not template_dir.exists():
        return []
    return [load_template_file(path) for path in sorted(template_dir.glob("*.yaml"))]


def _match_value(expected: Any, actual: str) -> float:
    if expected is None:
        return 0.0
    if expected == "*" or expected == actual:
        return 1.0
    if isinstance(expected, list) and actual in expected:
        return 1.0
    return 0.0


def match_templates(
    intent: UserIntent,
    template_dir: Path = TEMPLATE_DIR,
) -> list[TemplateCandidate]:
    candidates: list[TemplateCandidate] = []
    for path in sorted(template_dir.glob("*.yaml")) if template_dir.exists() else []:
        template = load_template_file(path)
        matches = template.get("matches", {})
        domain_score = _match_value(matches.get("domain"), intent.domain)
        action_score = _match_value(matches.get("action"), intent.action)
        deliverable_score = _match_value(matches.get("deliverable_type"), intent.deliverable_type)
        score = round((domain_score * 0.4) + (action_score * 0.35) + (deliverable_score * 0.25), 2)
        if score > 0:
            candidates.append(
                TemplateCandidate(
                    template_id=str(template["id"]),
                    family=str(template.get("family") or path.stem),
                    confidence=score,
                    path=path,
                    template=template,
                )
            )
    return sorted(candidates, key=lambda candidate: candidate.confidence, reverse=True)


def best_template(intent: UserIntent, min_confidence: float = 0.75) -> TemplateCandidate | None:
    candidates = match_templates(intent)
    if not candidates or candidates[0].confidence < min_confidence:
        return None
    return candidates[0]


def instantiate_template(intent: UserIntent, candidate: TemplateCandidate) -> PipelineGraph:
    template = candidate.template
    constraints = dict(intent.constraints)
    constraints["template_id"] = candidate.template_id
    constraints["template_budgets"] = template.get("budgets", {})
    graph_intent = intent.model_copy(update={"constraints": constraints})

    nodes = []
    for node_def in template.get("nodes", []):
        metadata = dict(node_def.get("metadata", {}))
        for key in ("fan_out", "description"):
            if key in node_def:
                metadata[key] = node_def[key]
        nodes.append(
            PipelineNode(
                id=node_def["id"],
                kind=node_def["kind"],
                capability=node_def["capability"],
                input_schema=node_def.get("input_schema", {}),
                output_schema=node_def.get("output_schema", {}),
                retry_policy=node_def.get("retry_policy", {}),
                timeout_s=int(node_def.get("timeout_s", 300)),
                max_revisions=int(node_def.get("max_revisions", 0)),
                requires_human_approval=bool(node_def.get("requires_human_approval", False)),
                cost_budget=node_def.get("cost_budget"),
                metadata=metadata,
            )
        )
    edges = [PipelineEdge(**edge_def) for edge_def in template.get("edges", [])]
    graph = PipelineGraph(
        id=str(template["id"]),
        template_family=candidate.family,
        intent=graph_intent,
        nodes=nodes,
        edges=edges,
        version=1,
    ).with_checksum()
    validation = validate_graph(graph)
    if not validation.valid:
        raise ValueError(f"Invalid template {candidate.template_id}: {validation.model_dump()}")
    return graph
