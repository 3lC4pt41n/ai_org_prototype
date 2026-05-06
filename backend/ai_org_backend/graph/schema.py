from __future__ import annotations

import hashlib
import json
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from ai_org_backend.intent.schema import UserIntent


NodeKind = Literal[
    "planner",
    "generator",
    "tool",
    "reviewer",
    "evaluator",
    "approval",
    "join",
    "router",
    "repair",
    "publish",
    "clarification",
]
EdgeType = Literal["control", "data", "feedback", "invalidates"]


class PipelineNode(BaseModel):
    id: str
    kind: NodeKind
    capability: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    retry_policy: dict[str, Any] = Field(default_factory=dict)
    timeout_s: int = 300
    max_revisions: int = 0
    requires_human_approval: bool = False
    cost_budget: Optional[dict[str, Any]] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PipelineEdge(BaseModel):
    source: str
    target: str
    condition: Optional[str] = None
    activation: Literal["all", "any"] = "all"
    edge_type: EdgeType = "control"


class PipelineGraph(BaseModel):
    id: str
    template_family: Optional[str] = None
    intent: UserIntent
    nodes: list[PipelineNode]
    edges: list[PipelineEdge]
    version: int = 1
    checksum: str = ""

    def checksum_payload(self) -> dict[str, Any]:
        return {
            "nodes": [node.model_dump(mode="json") for node in self.nodes],
            "edges": [edge.model_dump(mode="json") for edge in self.edges],
        }

    def compute_checksum(self) -> str:
        payload = json.dumps(self.checksum_payload(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def with_checksum(self) -> "PipelineGraph":
        data = self.model_dump(mode="json")
        data["checksum"] = self.compute_checksum()
        return PipelineGraph.model_validate(data)
