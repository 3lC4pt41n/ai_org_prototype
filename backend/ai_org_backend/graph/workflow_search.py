from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

from ai_org_backend.graph.schema import PipelineGraph
from ai_org_backend.graph.synthesizer import compile_graph
from ai_org_backend.graph.template_matcher import match_templates
from ai_org_backend.intent.schema import UserIntent


class WorkflowSearchLimits(BaseModel):
    max_candidates: int = Field(default=5, ge=1, le=20)
    max_iterations: int = Field(default=3, ge=1, le=10)
    min_score: float = Field(default=0.75, ge=0.0, le=1.0)


@dataclass(frozen=True)
class WorkflowSearchResult:
    selected_graph: PipelineGraph | None
    candidate_scores: list[tuple[str, float]]
    rejected_reason: str | None = None


def _score_graph(graph: PipelineGraph, template_confidence: float) -> float:
    approval_bonus = 0.05 if any(node.requires_human_approval for node in graph.nodes) else 0.0
    complexity_penalty = min(len(graph.nodes) / 100.0, 0.2)
    return round(max(0.0, min(1.0, template_confidence + approval_bonus - complexity_penalty)), 3)


def bounded_workflow_search(
    intent: UserIntent,
    limits: WorkflowSearchLimits | None = None,
) -> WorkflowSearchResult:
    limits = limits or WorkflowSearchLimits()
    candidates = match_templates(intent)[: limits.max_candidates]
    scores: list[tuple[str, float]] = []
    best_graph: PipelineGraph | None = None
    best_score = -1.0

    for candidate in candidates[: limits.max_iterations]:
        graph = compile_graph(intent)
        score = _score_graph(graph, candidate.confidence)
        scores.append((candidate.template_id, score))
        if score > best_score:
            best_score = score
            best_graph = graph

    if best_graph is None:
        try:
            best_graph = compile_graph(intent)
        except Exception as exc:
            return WorkflowSearchResult(
                selected_graph=None,
                candidate_scores=scores,
                rejected_reason=str(exc),
            )
        best_score = 0.75
        scores.append((best_graph.id, best_score))

    if best_score < limits.min_score:
        return WorkflowSearchResult(
            selected_graph=None,
            candidate_scores=scores,
            rejected_reason=f"best score {best_score} below minimum {limits.min_score}",
        )
    return WorkflowSearchResult(selected_graph=best_graph, candidate_scores=scores)
