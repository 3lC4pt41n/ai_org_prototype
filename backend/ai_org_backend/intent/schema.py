from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


Domain = Literal["software", "book", "research", "ops", "general"]
Action = Literal["create", "rework", "review", "continue", "summarize", "translate"]
Scale = Literal["small", "medium", "large"]
InteractionMode = Literal["auto", "manual", "hybrid"]
Risk = Literal["low", "medium", "high"]


class UserIntent(BaseModel):
    domain: Domain
    action: Action
    deliverable_type: str
    target_artifact_id: Optional[str] = None
    target_artifact_type: Optional[str] = None
    scale: Scale = "medium"
    interaction_mode: InteractionMode = "hybrid"
    risk: Risk = "medium"
    constraints: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    raw_request: str
