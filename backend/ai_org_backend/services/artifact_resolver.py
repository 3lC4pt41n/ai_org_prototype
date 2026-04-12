"""S3-03: Central Artifact Resolver.

Provides a single entry-point to load artifact content by pipeline phase,
by task description, or by task ID — avoiding the duplicated artifact-fetch
logic that was scattered across every agent module.

Usage::

    from ai_org_backend.services.artifact_resolver import load_by_phase

    vision_md = load_by_phase(purpose_id, "vision document")
    prd_md    = load_by_phase(purpose_id, "product requirements document")
    blueprint = load_by_phase(purpose_id, "architecture blueprint")
    review_md = load_by_phase(purpose_id, "architecture & domain review")

S-Sprint1 Fix #9: Added ``require_artifact`` parameter and
``ArtifactNotFoundError`` so callers can opt into strict mode that
fails explicitly instead of returning a silent None / empty string.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import desc
from sqlmodel import Session, func, select

from ai_org_backend.db import engine
from ai_org_backend.models import Artifact, Task

log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# S-Sprint1 Fix #9: Explicit exception for missing artifacts
# ──────────────────────────────────────────────────────────────────────

class ArtifactNotFoundError(Exception):
    """Raised when a required pipeline artifact is missing or empty."""

    def __init__(self, phase: str, purpose_id: str, reason: str = "not found"):
        self.phase = phase
        self.purpose_id = purpose_id
        self.reason = reason
        super().__init__(
            f"Required artifact for phase '{phase}' {reason} "
            f"(purpose={purpose_id})"
        )


def _latest_artifact(session: Session, task_id: str) -> Optional[Artifact]:
    """Return the most recently created artifact for a task."""
    return session.exec(
        select(Artifact)
        .where(Artifact.task_id == task_id)
        .order_by(desc(Artifact.created_at))
    ).first()


def _read_artifact_text(artifact: Artifact) -> str:
    """Read the text content of an artifact from disk."""
    from ai_org_backend.services.storage import resolve_for_read

    try:
        path = resolve_for_read(artifact.repo_path)
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        log.warning("Failed to read artifact %s (%s): %s", artifact.id, artifact.repo_path, exc)
        return ""


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────

def load_by_phase(
    purpose_id: str,
    phase_description: str,
    *,
    require_done: bool = False,
    require_released: bool = False,
    require_artifact: bool = False,
) -> Optional[str]:
    """Load the latest artifact text for a pipeline phase within a purpose.

    Parameters
    ----------
    purpose_id : str
        The purpose to search within.
    phase_description : str
        Case-insensitive task description (e.g. "Architecture Blueprint").
    require_done : bool
        If True, only consider tasks with status "done".
    require_released : bool
        If True, only consider artifacts where ``released=True``.
    require_artifact : bool
        **S-Sprint1 Fix #9** – If True, raise ``ArtifactNotFoundError``
        instead of returning None when the task or artifact is missing.
        This enables callers (agents) to fail fast with a clear error
        rather than silently proceeding with empty context.

    Returns
    -------
    str or None
        The artifact text content, or None if not found (and
        ``require_artifact`` is False).

    Raises
    ------
    ArtifactNotFoundError
        If ``require_artifact=True`` and the artifact cannot be loaded.
    """
    with Session(engine) as session:
        q = select(Task).where(
            Task.purpose_id == purpose_id,
            func.lower(Task.description) == phase_description.lower(),
        )
        if require_done:
            q = q.where(Task.status == "done")

        task = session.exec(q.order_by(desc(Task.created_at))).first()
        if not task:
            if require_artifact:
                raise ArtifactNotFoundError(
                    phase_description, purpose_id, reason="task not found"
                )
            return None

        artifact = _latest_artifact(session, task.id)
        if not artifact:
            if require_artifact:
                raise ArtifactNotFoundError(
                    phase_description, purpose_id, reason="no artifact on task"
                )
            return None
        if require_released and not artifact.released:
            if require_artifact:
                raise ArtifactNotFoundError(
                    phase_description, purpose_id, reason="artifact not released"
                )
            return None

    text = _read_artifact_text(artifact)
    if require_artifact and not text.strip():
        raise ArtifactNotFoundError(
            phase_description, purpose_id, reason="artifact file is empty"
        )
    return text


def load_by_task_id(task_id: str) -> Optional[str]:
    """Load the latest artifact text for a specific task."""
    with Session(engine) as session:
        artifact = _latest_artifact(session, task_id)
        if not artifact:
            return None
    return _read_artifact_text(artifact)


def load_artifact_metadata(
    purpose_id: str,
    phase_description: str,
) -> Optional[Artifact]:
    """Return the Artifact ORM object (without reading file content)."""
    with Session(engine) as session:
        task = session.exec(
            select(Task).where(
                Task.purpose_id == purpose_id,
                func.lower(Task.description) == phase_description.lower(),
            ).order_by(desc(Task.created_at))
        ).first()
        if not task:
            return None
        return _latest_artifact(session, task.id)


def load_all_phase_artifacts(purpose_id: str) -> dict[str, str]:
    """Load all pipeline-phase artifacts for a purpose.

    Returns a dict mapping phase description (lowercased) → artifact text.
    """
    phases = [
        "vision document",
        "product requirements document",
        "architecture blueprint",
        "architecture & domain review",
        "implementation plan",
    ]
    result: dict[str, str] = {}
    for phase in phases:
        text = load_by_phase(purpose_id, phase)
        if text:
            result[phase] = text
    return result
