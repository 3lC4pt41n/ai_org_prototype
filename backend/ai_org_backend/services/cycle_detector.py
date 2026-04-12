"""S3-06: Dependency cycle detection using DFS.

Validates task dependency graphs for cycles before persisting them.
Called after schema validation in the planner to catch invalid
dependency graphs early.

Usage::

    from ai_org_backend.services.cycle_detector import detect_cycles, validate_no_cycles

    tasks = [{"id": "a", "depends_on": "b"}, {"id": "b", "depends_on": "a"}]
    cycles = detect_cycles(tasks)
    # cycles = [["a", "b", "a"]]

    validate_no_cycles(tasks)
    # raises CyclicDependencyError
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


class CyclicDependencyError(ValueError):
    """Raised when a dependency cycle is detected in the task graph."""

    def __init__(self, cycles: list[list[str]]):
        self.cycles = cycles
        cycle_strs = [" → ".join(c) for c in cycles[:3]]
        super().__init__(f"Cyclic dependencies detected: {'; '.join(cycle_strs)}")


def _build_adjacency(tasks: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Build adjacency list from planner task list."""
    adj: dict[str, list[str]] = {}
    for t in tasks:
        tid = str(t.get("id", ""))
        dep = t.get("depends_on")
        if tid:
            adj.setdefault(tid, [])
        if dep and tid:
            dep_str = str(dep)
            adj.setdefault(dep_str, [])
            adj[dep_str].append(tid)
    return adj


def detect_cycles(tasks: list[dict[str, Any]]) -> list[list[str]]:
    """Detect all cycles in the task dependency graph using DFS.

    Returns a list of cycles, where each cycle is a list of task IDs
    forming a loop (e.g. ["a", "b", "c", "a"]).
    """
    adj = _build_adjacency(tasks)
    visited: set[str] = set()
    in_stack: set[str] = set()
    stack: list[str] = []
    cycles: list[list[str]] = []

    def dfs(node: str) -> None:
        visited.add(node)
        in_stack.add(node)
        stack.append(node)

        for neighbor in adj.get(node, []):
            if neighbor not in visited:
                dfs(neighbor)
            elif neighbor in in_stack:
                # Found a cycle: extract the cycle from the stack
                cycle_start = stack.index(neighbor)
                cycle = stack[cycle_start:] + [neighbor]
                cycles.append(cycle)

        stack.pop()
        in_stack.discard(node)

    for node in adj:
        if node not in visited:
            dfs(node)

    return cycles


def validate_no_cycles(tasks: list[dict[str, Any]]) -> None:
    """Validate that the task graph has no cycles.

    Raises ``CyclicDependencyError`` if cycles are found.
    """
    cycles = detect_cycles(tasks)
    if cycles:
        log.warning("Detected %d cycle(s) in task dependencies", len(cycles))
        raise CyclicDependencyError(cycles)


def validate_refs(tasks: list[dict[str, Any]]) -> list[str]:
    """S3-05: Validate that all depends_on references point to existing task IDs.

    Returns a list of warnings for dangling references.
    """
    known_ids = {str(t.get("id", "")) for t in tasks}
    warnings: list[str] = []
    for t in tasks:
        dep = t.get("depends_on")
        if dep and str(dep) not in known_ids:
            warnings.append(
                f"Task '{t.get('id')}' depends on unknown task '{dep}'"
            )
    return warnings
