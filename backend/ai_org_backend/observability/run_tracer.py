from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, Field


SENSITIVE_KEYS = {"prompt", "raw_request", "content", "message", "email", "token", "password"}


def scrub_attributes(attributes: dict[str, Any], allowlist: set[str] | None = None) -> dict[str, Any]:
    allowlist = allowlist or set()
    scrubbed: dict[str, Any] = {}
    for key, value in attributes.items():
        key_lower = key.lower()
        if key in allowlist:
            scrubbed[key] = value
        elif any(sensitive in key_lower for sensitive in SENSITIVE_KEYS):
            scrubbed[key] = "<redacted>"
        else:
            scrubbed[key] = value
    return scrubbed


class RunSpan(BaseModel):
    span_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    trace_id: str
    parent_span_id: str | None = None
    name: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=datetime.utcnow)
    ended_at: datetime | None = None


class RunTracer(Protocol):
    def start_span(
        self,
        trace_id: str,
        name: str,
        *,
        parent_span_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> RunSpan: ...

    def end_span(self, span_id: str) -> None: ...

    def export_trace(self, trace_id: str) -> dict[str, Any]: ...


class InMemoryRunTracer:
    def __init__(self, max_trace_bytes: int = 5_000_000, pii_allowlist: set[str] | None = None):
        self.max_trace_bytes = max_trace_bytes
        self.pii_allowlist = pii_allowlist or set()
        self._spans: dict[str, RunSpan] = {}

    def start_span(
        self,
        trace_id: str,
        name: str,
        *,
        parent_span_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> RunSpan:
        span = RunSpan(
            trace_id=trace_id,
            name=name,
            parent_span_id=parent_span_id,
            attributes=scrub_attributes(attributes or {}, self.pii_allowlist),
        )
        self._spans[span.span_id] = span
        return span

    def end_span(self, span_id: str) -> None:
        span = self._spans[span_id]
        self._spans[span_id] = span.model_copy(update={"ended_at": datetime.utcnow()})

    def export_trace(self, trace_id: str) -> dict[str, Any]:
        spans = [span.model_dump(mode="json") for span in self._spans.values() if span.trace_id == trace_id]
        payload = {"trace_id": trace_id, "spans": spans}
        size = len(json.dumps(payload, sort_keys=True).encode("utf-8"))
        if size > self.max_trace_bytes:
            return {
                "trace_id": trace_id,
                "truncated": True,
                "span_count": len(spans),
                "size_bytes": size,
                "spans": [],
            }
        payload["size_bytes"] = size
        payload["truncated"] = False
        return payload
