from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from .schema import PipelineGraph


RunState = Literal["queued", "running", "succeeded", "failed", "cancelled", "replaying"]


class RunStatus(BaseModel):
    run_id: str
    graph_id: str
    state: RunState
    current_node: str | None = None
    terminal_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowEngine(Protocol):
    def submit(self, graph: PipelineGraph, payload: dict[str, Any]) -> str: ...

    def status(self, run_id: str) -> RunStatus: ...

    def cancel(self, run_id: str) -> None: ...

    def replay(self, run_id: str, from_node: str | None = None) -> str: ...


class CeleryEngine:
    """Compatibility adapter placeholder for the current Celery runtime."""

    def __init__(self) -> None:
        self._runs: dict[str, RunStatus] = {}

    def submit(self, graph: PipelineGraph, payload: dict[str, Any]) -> str:
        checked_graph = graph.with_checksum()
        run_id = f"celery:{checked_graph.id}:{checked_graph.checksum[:12]}"
        first_node = checked_graph.nodes[0].id if checked_graph.nodes else None
        self._runs[run_id] = RunStatus(
            run_id=run_id,
            graph_id=checked_graph.id,
            state="queued",
            current_node=first_node,
            metadata={"payload_keys": sorted(payload.keys())},
        )
        return run_id

    def status(self, run_id: str) -> RunStatus:
        return self._runs.get(
            run_id,
            RunStatus(run_id=run_id, graph_id="", state="failed", terminal_reason="unknown_run"),
        )

    def cancel(self, run_id: str) -> None:
        status = self.status(run_id)
        self._runs[run_id] = status.model_copy(update={"state": "cancelled"})

    def replay(self, run_id: str, from_node: str | None = None) -> str:
        status = self.status(run_id)
        replay_id = f"{run_id}:replay:{from_node or 'start'}"
        self._runs[replay_id] = RunStatus(
            run_id=replay_id,
            graph_id=status.graph_id,
            state="replaying",
            current_node=from_node or status.current_node,
            metadata={"source_run_id": run_id},
        )
        return replay_id
