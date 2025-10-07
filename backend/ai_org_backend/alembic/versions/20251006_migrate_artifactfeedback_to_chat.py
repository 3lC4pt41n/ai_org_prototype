"""Backfill ArtifactFeedback entries into chat tables."""

from __future__ import annotations

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session


revision: str = "20251006_migrate_artifactfeedback_to_chat"
down_revision: Union[str, Sequence[str], None] = "20251004_artifact_release_flag"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _parse_version(value: object) -> int | None:
    if isinstance(value, dict) and "version" in value:
        try:
            return int(value.get("version"))
        except (TypeError, ValueError):
            return None
    return None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("artifactfeedback"):
        return

    metadata = sa.MetaData()
    artifactfeedback = sa.Table("artifactfeedback", metadata, autoload_with=bind)
    chatmessage = sa.Table("chatmessage", metadata, autoload_with=bind)
    chatmessageartifact = sa.Table("chatmessageartifact", metadata, autoload_with=bind)
    artifact = sa.Table("artifact", metadata, autoload_with=bind)
    task = sa.Table("task", metadata, autoload_with=bind)

    session = Session(bind=bind)
    try:
        stmt = (
            sa.select(
                artifactfeedback.c.id,
                artifactfeedback.c.artifact_id,
                artifactfeedback.c.tenant_id,
                artifactfeedback.c.author,
                artifactfeedback.c.version,
                artifactfeedback.c.content,
                artifactfeedback.c.created_at,
                artifact.c.task_id,
                task.c.purpose_id,
            )
            .select_from(
                artifactfeedback.join(
                    artifact,
                    artifact.c.id == artifactfeedback.c.artifact_id,
                    isouter=True,
                ).join(task, task.c.id == artifact.c.task_id, isouter=True)
            )
            .order_by(artifactfeedback.c.created_at, artifactfeedback.c.id)
        )
        feedback_rows = session.execute(stmt).mappings().all()
        if not feedback_rows:
            session.commit()
            return

        keys = {
            (row["tenant_id"], row["artifact_id"])
            for row in feedback_rows
            if row["tenant_id"] and row["artifact_id"]
        }
        max_versions: dict[tuple[str, str], int] = {}
        if keys:
            artifact_ids = {artifact_id for _, artifact_id in keys}
            existing_stmt = (
                sa.select(
                    chatmessage.c.metadata,
                    chatmessage.c.tenant_id,
                    chatmessage.c.artifact_id.label("direct_artifact_id"),
                    chatmessageartifact.c.artifact_id.label("linked_artifact_id"),
                )
                .select_from(
                    chatmessage.outerjoin(
                        chatmessageartifact,
                        chatmessageartifact.c.chat_message_id == chatmessage.c.id,
                    )
                )
                .where(chatmessage.c.intent == "feedback")
                .where(
                    sa.or_(
                        chatmessage.c.artifact_id.in_(artifact_ids),
                        chatmessageartifact.c.artifact_id.in_(artifact_ids),
                    )
                )
            )
            existing_rows = session.execute(existing_stmt).mappings().all()
            for row in existing_rows:
                meta = row["metadata"]
                tenant_id = row["tenant_id"]
                artifact_id = row["direct_artifact_id"] or row["linked_artifact_id"]
                if not tenant_id or not artifact_id:
                    continue
                parsed = _parse_version(meta)
                if parsed is None:
                    continue
                key = (tenant_id, artifact_id)
                if parsed > max_versions.get(key, 0):
                    max_versions[key] = parsed

        for row in feedback_rows:
            tenant_id = row["tenant_id"]
            artifact_id = row["artifact_id"]
            if not tenant_id or not artifact_id:
                continue
            key = (tenant_id, artifact_id)
            desired_version = row.get("version") or 1
            if not isinstance(desired_version, int):
                try:
                    desired_version = int(desired_version)
                except (TypeError, ValueError):
                    desired_version = 1
            current_max = max_versions.get(key, 0)
            if desired_version <= current_max:
                desired_version = current_max + 1
            max_versions[key] = desired_version

            content = row.get("content") or ""
            if not content:
                continue

            message_id = uuid.uuid4().hex[:8]
            session.execute(
                chatmessage.insert().values(
                    id=message_id,
                    tenant_id=tenant_id,
                    purpose_id=row.get("purpose_id"),
                    artifact_id=artifact_id,
                    task_id=row.get("task_id"),
                    role="user",
                    scope="artifact",
                    intent="feedback",
                    content=content,
                    metadata={
                        "author": row.get("author"),
                        "version": desired_version,
                        "legacy_feedback_id": row.get("id"),
                    },
                    created_at=row.get("created_at"),
                )
            )
            session.execute(
                chatmessageartifact.insert().values(
                    chat_message_id=message_id,
                    artifact_id=artifact_id,
                )
            )

        session.commit()
    finally:
        session.close()


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("chatmessage"):
        return

    metadata = sa.MetaData()
    chatmessage = sa.Table("chatmessage", metadata, autoload_with=bind)
    chatmessageartifact = sa.Table("chatmessageartifact", metadata, autoload_with=bind)

    session = Session(bind=bind)
    try:
        stmt = sa.select(chatmessage.c.id, chatmessage.c.metadata).where(
            chatmessage.c.intent == "feedback"
        )
        rows = session.execute(stmt).mappings().all()
        message_ids = [
            row["id"]
            for row in rows
            if isinstance(row.get("metadata"), dict)
            and row["metadata"].get("legacy_feedback_id")
        ]
        if message_ids:
            session.execute(
                chatmessageartifact.delete().where(
                    chatmessageartifact.c.chat_message_id.in_(message_ids)
                )
            )
            session.execute(
                chatmessage.delete().where(chatmessage.c.id.in_(message_ids))
            )
        session.commit()
    finally:
        session.close()
