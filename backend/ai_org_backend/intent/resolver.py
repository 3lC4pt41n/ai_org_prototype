from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from pydantic import BaseModel, Field

from .extractor import IntentSignals


ArtifactLookup = Callable[[str], Mapping[str, Any] | None]


class ResolvedContext(BaseModel):
    target_artifact_id: str | None = None
    target_artifact_type: str | None = None
    target_artifact_exists: bool | None = None
    latest_version_id: str | None = None
    notes: list[str] = Field(default_factory=list)


def resolve_context(
    signals: IntentSignals,
    artifact_lookup: ArtifactLookup | None = None,
) -> ResolvedContext:
    if not signals.target_artifact_id:
        return ResolvedContext(
            target_artifact_type=signals.target_artifact_type,
            notes=["no_explicit_artifact_reference"],
        )

    if artifact_lookup is None:
        return ResolvedContext(
            target_artifact_id=signals.target_artifact_id,
            target_artifact_type=signals.target_artifact_type,
            target_artifact_exists=None,
            notes=["artifact_lookup_not_configured"],
        )

    artifact = artifact_lookup(signals.target_artifact_id)
    if artifact is None:
        return ResolvedContext(
            target_artifact_id=signals.target_artifact_id,
            target_artifact_type=signals.target_artifact_type,
            target_artifact_exists=False,
            notes=["artifact_reference_not_found"],
        )

    artifact_type = artifact.get("type") or artifact.get("artifact_type") or signals.target_artifact_type
    latest_version = artifact.get("latest_version_id") or artifact.get("version_id")
    return ResolvedContext(
        target_artifact_id=signals.target_artifact_id,
        target_artifact_type=str(artifact_type) if artifact_type else None,
        target_artifact_exists=True,
        latest_version_id=str(latest_version) if latest_version else None,
        notes=["artifact_reference_resolved"],
    )
