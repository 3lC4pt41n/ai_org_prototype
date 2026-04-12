"""S4-01 / S4-02 / S4-03: Central approval service.

Provides a single ``approve_artifact()`` entry-point that:

- Validates the artifact exists and is not already released (409 Conflict).
- Supports idempotency tokens to prevent double-approvals (S4-03).
- Marks the artifact as ``released=True``.
- Updates the parent task status to "done" and notes to "approved".
- Clears the orchestrator pause flag so the scheduler picks up the next phase.
- Returns a structured ``ApprovalResult`` for the caller.

All approval endpoints (chat.py, artifact_bridge.py, pipeline.py) should delegate
to this service instead of duplicating the release logic.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Optional

from sqlmodel import Session

from ai_org_backend.db import engine
from ai_org_backend.models import Artifact, Purpose, Task
from ai_org_backend.redis_client import pool

logger = logging.getLogger(__name__)

# S4-03: Idempotency token TTL (seconds) – 1 hour
_IDEMPOTENCY_TTL = 3600


class ApprovalError(Exception):
    """Base error for approval failures."""


class AlreadyReleasedError(ApprovalError):
    """Artifact was already approved/released."""


class ArtifactNotFoundError(ApprovalError):
    """Artifact ID does not exist."""


class DuplicateApprovalError(ApprovalError):
    """A request with the same idempotency token was already processed."""


@dataclass
class ApprovalResult:
    """Structured result returned by ``approve_artifact()``."""

    artifact_id: str
    task_id: str
    purpose_id: Optional[str] = None
    previously_released: bool = False
    idempotent_hit: bool = False
    pause_cleared: bool = False
    phase_hint: Optional[str] = None  # e.g. "vision", "prd", "architecture", "review"


def _detect_phase_hint(task: Task, artifact: Artifact) -> Optional[str]:
    """Detect which pipeline phase this artifact belongs to."""
    task_desc = (task.description or "").lower()
    repo_path = (artifact.repo_path or "").lower()

    if "vision" in task_desc or "vision" in repo_path:
        return "vision"
    if "product requirements" in task_desc or "requirements" in repo_path:
        return "prd"
    if "architecture blueprint" in task_desc or "blueprints/" in repo_path:
        return "architecture"
    if "architecture & domain review" in task_desc or "review" in repo_path:
        return "review"
    return None


def approve_artifact(
    artifact_id: str,
    *,
    tenant_id: Optional[str] = None,
    purpose_id: Optional[str] = None,
    idempotency_token: Optional[str] = None,
    clear_pause: bool = True,
    session: Optional[Session] = None,
) -> ApprovalResult:
    """S4-01: Central approve-artifact service function.

    Parameters
    ----------
    artifact_id : str
        ID of the artifact to approve / release.
    tenant_id : str, optional
        Tenant context (resolved from task if omitted).
    purpose_id : str, optional
        Purpose context (resolved from task if omitted).
    idempotency_token : str, optional
        S4-03: Client-provided idempotency token.  If the same token was
        already used successfully, the function returns the cached result
        without modifying any state.
    clear_pause : bool
        Whether to clear the orchestrator pause flag after approval.
    session : Session, optional
        Existing DB session to use.  If ``None``, a new session is created.

    Returns
    -------
    ApprovalResult

    Raises
    ------
    ArtifactNotFoundError
        If the artifact does not exist.
    AlreadyReleasedError
        If the artifact is already released (and no idempotency token matches).
    """
    # S4-03: Check idempotency token
    if idempotency_token:
        redis_key = f"approval_idem:{idempotency_token}"
        try:
            cached = pool.get(redis_key)
            if cached:
                logger.info(
                    "Idempotent approval hit for token %s → artifact %s",
                    idempotency_token,
                    cached.decode() if isinstance(cached, bytes) else cached,
                )
                return ApprovalResult(
                    artifact_id=artifact_id,
                    task_id="",
                    idempotent_hit=True,
                )
        except Exception:
            pass  # Redis unavailable – proceed without idempotency

    owns_session = session is None
    if owns_session:
        session = Session(engine)

    try:
        artifact = session.get(Artifact, artifact_id)
        if not artifact:
            raise ArtifactNotFoundError(f"Artifact {artifact_id} not found")

        task = session.get(Task, artifact.task_id)
        if not task:
            raise ArtifactNotFoundError(
                f"Task {artifact.task_id} for artifact {artifact_id} not found"
            )

        # Resolve tenant/purpose from task if not provided
        resolved_tenant = tenant_id or task.tenant_id
        resolved_purpose = purpose_id or task.purpose_id

        # Already released?
        if artifact.released:
            logger.info("Artifact %s already released", artifact_id)
            return ApprovalResult(
                artifact_id=artifact_id,
                task_id=task.id,
                purpose_id=resolved_purpose,
                previously_released=True,
                phase_hint=_detect_phase_hint(task, artifact),
            )

        # ── Core approval logic ──
        artifact.released = True
        session.add(artifact)

        if task.status != "done":
            task.status = "done"
        if task.notes and "awaiting_approval" in task.notes:
            task.notes = task.notes.replace("awaiting_approval", "approved")
        elif task.notes and "approved" not in (task.notes or "").lower():
            task.notes = f"{task.notes} | approved"
        elif not task.notes:
            task.notes = "approved"
        session.add(task)

        session.commit()

        phase_hint = _detect_phase_hint(task, artifact)

        # ── Clear pause flag ──
        pause_cleared = False
        if clear_pause and resolved_tenant and resolved_purpose:
            try:
                pool.delete(f"pause:{resolved_tenant}:{resolved_purpose}")
                pause_cleared = True
            except Exception as exc:
                logger.warning("Failed to clear pause flag: %s", exc)

        # S4-03: Store idempotency token
        if idempotency_token:
            try:
                pool.set(
                    f"approval_idem:{idempotency_token}",
                    artifact_id,
                    ex=_IDEMPOTENCY_TTL,
                )
            except Exception:
                pass  # Redis unavailable

        logger.info(
            "Artifact %s approved (task=%s, phase=%s, purpose=%s)",
            artifact_id,
            task.id,
            phase_hint,
            resolved_purpose,
        )

        return ApprovalResult(
            artifact_id=artifact_id,
            task_id=task.id,
            purpose_id=resolved_purpose,
            pause_cleared=pause_cleared,
            phase_hint=phase_hint,
        )

    except ApprovalError:
        raise
    except Exception as exc:
        if owns_session:
            session.rollback()
        logger.error("approve_artifact failed: %s", exc)
        raise
    finally:
        if owns_session:
            session.close()
