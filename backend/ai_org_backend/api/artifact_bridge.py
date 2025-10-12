"""Bridge API for exposing artifact details and feedback messages.

This module uses lightweight ``text`` queries so it can operate against
slightly differing database schemas. It focuses on the minimal columns that
exist in most deployments.
"""
from __future__ import annotations

from importlib import import_module
from importlib.util import find_spec
from typing import Callable, Dict, Iterable

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlmodel import Session

router = APIRouter(prefix="/api", tags=["artifact-bridge"])


# ---------------------------------------------------------------------------
# Session dependency resolution
# ---------------------------------------------------------------------------

def _resolve_session_dependency() -> Callable[..., Iterable[Session]]:
    """Locate a ``get_session`` dependency or build one from the engine."""

    for module_name in ("ai_org_backend.dependencies", "ai_org_backend.api.dependencies"):
        spec = find_spec(module_name)
        if spec is None:
            continue
        module = import_module(module_name)
        if hasattr(module, "get_session"):
            return getattr(module, "get_session")  # type: ignore[return-value]

    spec = find_spec("ai_org_backend.db")
    if spec is not None:
        module = import_module("ai_org_backend.db")
        engine = getattr(module, "engine", None)
        if engine is not None:
            def _default_get_session() -> Iterable[Session]:
                with Session(engine) as session:
                    yield session

            return _default_get_session

    raise RuntimeError("Database session dependency could not be resolved")


def _row_to_dict(row) -> Dict:
    """Convert a SQLAlchemy row mapping to a dictionary."""

    if hasattr(row, "_mapping"):
        return dict(row._mapping)
    return dict(row)


get_session = _resolve_session_dependency()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class FeedbackBody(BaseModel):
    content: str = Field(..., alias="message")
    role: str | None = "user"
    intent: str | None = "feedback"
    scope: str | None = None

    model_config = ConfigDict(populate_by_name=True)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/artifact/{artifact_id}")
@router.get("/artifacts/{artifact_id}")
def get_artifact_by_id(artifact_id: str, session: Session = Depends(get_session)) -> Dict:
    """Return the stored representation of an artifact."""

    query = text(
        """
        SELECT a.id,
               a.task_id,
               a.repo_path AS filename,
               a.media_type AS mime,
               a.sha256,
               a.created_at,
               t.purpose_id,
               p.tenant_id
        FROM artifact AS a
        JOIN task AS t ON t.id = a.task_id
        JOIN purpose AS p ON p.id = t.purpose_id
        WHERE a.id = :id
        """
    )
    result = session.execute(query, {"id": artifact_id}).mappings().first()
    if result is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return _row_to_dict(result)


@router.get("/artifacts/{artifact_id}/feedback")
def get_feedback_for_artifact(artifact_id: str, session: Session = Depends(get_session)) -> Dict:
    """Return chat messages linked to an artifact via the join table."""

    query = text(
        """
        SELECT cm.*
        FROM chatmessage AS cm
        WHERE cm.id IN (
            SELECT cma.chat_message_id
            FROM chatmessageartifact AS cma
            WHERE cma.artifact_id = :aid
        )
        ORDER BY cm.created_at ASC NULLS FIRST, cm.id ASC
        """
    )
    rows = session.execute(query, {"aid": artifact_id}).mappings().all()
    return {"messages": [_row_to_dict(row) for row in rows]}


@router.post("/artifacts/{artifact_id}/feedback", status_code=201)
def post_feedback_for_artifact(
    artifact_id: str,
    body: FeedbackBody = Body(...),
    session: Session = Depends(get_session),
) -> Dict:
    """Store a feedback chat message and link it to the artifact."""

    meta_query = text(
        """
        SELECT t.purpose_id,
               p.tenant_id
        FROM artifact AS a
        JOIN task AS t ON t.id = a.task_id
        JOIN purpose AS p ON p.id = t.purpose_id
        WHERE a.id = :id
        """
    )
    meta = session.execute(meta_query, {"id": artifact_id}).mappings().first()
    if meta is None:
        raise HTTPException(status_code=404, detail="Artifact not found")

    message = (body.content or "").strip()
    if not message:
        raise HTTPException(status_code=422, detail="'content' is required")

    role = (body.role or "user").strip() or "user"
    intent = (body.intent or "feedback").strip() or "feedback"
    scope = (body.scope or "artifact").strip() or "artifact"

    insert_message = text(
        """
        INSERT INTO chatmessage (purpose_id, tenant_id, role, content, intent, scope, created_at)
        VALUES (:pid, :tid, :role, :content, :intent, :scope, NOW())
        RETURNING id
        """
    )

    try:
        message_id = session.execute(
            insert_message,
            {
                "pid": meta["purpose_id"],
                "tid": meta["tenant_id"],
                "role": role,
                "content": message,
                "intent": intent,
                "scope": scope,
            },
        ).scalar_one()
    except Exception as exc:  # pragma: no cover - database schema mismatch
        raise HTTPException(
            status_code=500,
            detail=(
                "Failed to insert chatmessage (adjust the insert columns to match "
                f"your schema): {exc}"
            ),
        ) from exc

    try:
        session.execute(
            text(
                "INSERT INTO chatmessageartifact (chat_message_id, artifact_id) "
                "VALUES (:cmid, :aid)"
            ),
            {"cmid": message_id, "aid": artifact_id},
        )
        session.commit()
    except Exception as exc:  # pragma: no cover - database schema mismatch
        session.rollback()
        raise HTTPException(
            status_code=500, detail=f"Failed to link chatmessage to artifact: {exc}"
        ) from exc

    return {"id": str(message_id), "artifact_id": artifact_id, "status": "ok"}
