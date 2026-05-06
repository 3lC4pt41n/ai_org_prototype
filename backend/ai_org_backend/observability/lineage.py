from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


LineageState = Literal["START", "COMPLETE", "FAIL"]


class LineageDataset(BaseModel):
    namespace: str = "ai_org.artifacts"
    name: str
    facets: dict[str, str] = Field(default_factory=dict)


class LineageEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    event_type: LineageState
    event_time: datetime = Field(default_factory=datetime.utcnow)
    run_id: str
    job_name: str
    inputs: list[LineageDataset] = Field(default_factory=list)
    outputs: list[LineageDataset] = Field(default_factory=list)


class OpenLineageEmitter:
    """OpenLineage-shaped in-memory emitter for future transport adapters."""

    def __init__(self) -> None:
        self.events: list[LineageEvent] = []

    def emit(
        self,
        *,
        event_type: LineageState,
        run_id: str,
        job_name: str,
        inputs: list[str] | None = None,
        outputs: list[str] | None = None,
    ) -> LineageEvent:
        event = LineageEvent(
            event_type=event_type,
            run_id=run_id,
            job_name=job_name,
            inputs=[LineageDataset(name=item) for item in inputs or []],
            outputs=[LineageDataset(name=item) for item in outputs or []],
        )
        self.events.append(event)
        return event
