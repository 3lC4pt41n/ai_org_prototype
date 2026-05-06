from __future__ import annotations

import operator
from collections import defaultdict, deque
from typing import Literal

from pydantic import BaseModel, Field, model_validator


ArtifactStatus = Literal["fresh", "stale", "invalidated", "archived"]
DependencyKind = Literal["derived_from", "invalidates"]
TerminalStatus = Literal["converged", "revision_limit_reached", "budget_exceeded"]


class RevisionLimitPolicy(BaseModel):
    max_revisions: int = Field(gt=0)
    convergence_predicate: str = Field(min_length=1)
    cost_budget: dict[str, float] = Field(min_length=1)

    @model_validator(mode="after")
    def require_all_loop_bounds(self) -> "RevisionLimitPolicy":
        if not self.convergence_predicate.strip():
            raise ValueError("convergence_predicate is required")
        if not self.cost_budget:
            raise ValueError("cost_budget is required")
        return self


class ArtifactDependency(BaseModel):
    parent_id: str
    child_id: str
    kind: DependencyKind = "derived_from"


class ArtifactGraphResult(BaseModel):
    changed_artifact_id: str
    stale_artifact_ids: list[str]
    invalidated_artifact_ids: list[str]
    statuses: dict[str, ArtifactStatus]


class ReworkDecision(BaseModel):
    should_continue: bool
    terminal_status: TerminalStatus | None = None
    requires_approval: bool = False
    reason: str


class ArtifactGraph:
    """In-memory artifact dependency service used by Phase 4 and tests."""

    def __init__(self) -> None:
        self._statuses: dict[str, ArtifactStatus] = {}
        self._children: dict[str, list[ArtifactDependency]] = defaultdict(list)

    def add_artifact(self, artifact_id: str, status: ArtifactStatus = "fresh") -> None:
        self._statuses[artifact_id] = status

    def add_dependency(
        self,
        parent_id: str,
        child_id: str,
        kind: DependencyKind = "derived_from",
    ) -> None:
        self._statuses.setdefault(parent_id, "fresh")
        self._statuses.setdefault(child_id, "fresh")
        self._children[parent_id].append(
            ArtifactDependency(parent_id=parent_id, child_id=child_id, kind=kind)
        )

    def downstream(self, artifact_id: str) -> list[ArtifactDependency]:
        result: list[ArtifactDependency] = []
        queue = deque(self._children.get(artifact_id, []))
        seen: set[tuple[str, str]] = set()
        while queue:
            dependency = queue.popleft()
            key = (dependency.parent_id, dependency.child_id)
            if key in seen:
                continue
            seen.add(key)
            result.append(dependency)
            queue.extend(self._children.get(dependency.child_id, []))
        return result

    def mark_downstream_stale(self, changed_artifact_id: str) -> ArtifactGraphResult:
        stale: list[str] = []
        invalidated: list[str] = []
        for dependency in self.downstream(changed_artifact_id):
            if dependency.kind == "invalidates":
                self._statuses[dependency.child_id] = "invalidated"
                invalidated.append(dependency.child_id)
            else:
                self._statuses[dependency.child_id] = "stale"
                stale.append(dependency.child_id)
        self._statuses.setdefault(changed_artifact_id, "fresh")
        return ArtifactGraphResult(
            changed_artifact_id=changed_artifact_id,
            stale_artifact_ids=stale,
            invalidated_artifact_ids=invalidated,
            statuses=dict(self._statuses),
        )

    def lowest_recompute_points(self, changed_artifact_id: str) -> list[str]:
        direct = self._children.get(changed_artifact_id, [])
        return [dependency.child_id for dependency in direct if dependency.kind == "derived_from"]


_OPS = {
    ">=": operator.ge,
    "<=": operator.le,
    ">": operator.gt,
    "<": operator.lt,
    "==": operator.eq,
}


def _predicate_matches(predicate: str, score: float) -> bool:
    text = predicate.replace(" ", "")
    for symbol, op in _OPS.items():
        if text.startswith(f"score{symbol}"):
            try:
                threshold = float(text.split(symbol, 1)[1])
            except ValueError:
                return False
            return bool(op(score, threshold))
    return False


def evaluate_rework_iteration(
    *,
    policy: RevisionLimitPolicy,
    revision_count: int,
    score: float,
    spent: dict[str, float] | None = None,
) -> ReworkDecision:
    spent = spent or {}
    if _predicate_matches(policy.convergence_predicate, score):
        return ReworkDecision(
            should_continue=False,
            terminal_status="converged",
            reason="convergence_predicate matched",
        )
    for key, budget in policy.cost_budget.items():
        if float(spent.get(key, 0.0)) > float(budget):
            return ReworkDecision(
                should_continue=False,
                terminal_status="budget_exceeded",
                requires_approval=True,
                reason=f"cost budget exceeded for {key}",
            )
    if revision_count >= policy.max_revisions:
        return ReworkDecision(
            should_continue=False,
            terminal_status="revision_limit_reached",
            reason="max_revisions reached",
        )
    return ReworkDecision(should_continue=True, reason="continue bounded rework")
