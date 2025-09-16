import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from pydantic import ConfigDict
from sqlmodel import Field, Relationship, SQLModel


# Helper: ensure SA enums use lowercase values of our StrEnums
def _values(enum_cls: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_cls]


if TYPE_CHECKING:  # pragma: no cover
    from .artifact import Artifact


class ChatRole(StrEnum):
    """Role of a chat message author."""

    USER = "user"
    ASSISTANT = "assistant"
    AGENT = "agent"


class ChatScope(StrEnum):
    """Scope in which the chat message should be interpreted."""

    GLOBAL = "global"
    ARTIFACT = "artifact"
    MIXED = "mixed"


class ChatIntent(StrEnum):
    """High level intent of the chat message."""

    QUESTION = "question"
    FEEDBACK = "feedback"
    NOTE = "note"
    APPROVAL = "approval"


class ChatMessageArtifact(SQLModel, table=True):  # type: ignore[call-arg]
    """Join table linking chat messages to artifacts."""

    chat_message_id: str = Field(foreign_key="chatmessage.id", primary_key=True)
    artifact_id: str = Field(foreign_key="artifact.id", primary_key=True)


class ChatMessage(SQLModel, table=True):  # type: ignore[call-arg]
    """Chat message in an interactive conversation."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8], primary_key=True)
    tenant_id: str = Field(foreign_key="tenant.id", nullable=False)
    purpose_id: Optional[str] = Field(default=None, foreign_key="purpose.id")
    artifact_id: Optional[str] = Field(default=None, foreign_key="artifact.id")
    task_id: Optional[str] = Field(default=None, foreign_key="task.id")
    # Map to Postgres ENUMs using the lowercase values to match existing DB
    role: ChatRole = Field(
        sa_column=sa.Column(
            sa.Enum(ChatRole, name="chatrole", values_callable=_values),
            nullable=False,
        ),
    )
    scope: ChatScope = Field(
        default=ChatScope.GLOBAL,
        sa_column=sa.Column(
            sa.Enum(ChatScope, name="chatscope", values_callable=_values),
            nullable=False,
        ),
    )
    intent: ChatIntent = Field(
        default=ChatIntent.QUESTION,
        sa_column=sa.Column(
            sa.Enum(ChatIntent, name="chatintent", values_callable=_values),
            nullable=False,
        ),
    )
    content: str = Field(nullable=False, max_length=5000)
    metadata_: dict | None = Field(
        default=None,
        sa_column=sa.Column("metadata", JSONB, nullable=True),
        alias="metadata",
    )
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    artifacts: list["Artifact"] = Relationship(
        back_populates="messages", link_model=ChatMessageArtifact
    )


class ChatThreadContext(SQLModel, table=True):  # type: ignore[call-arg]
    """Summary context for chat threads."""

    purpose_id: str = Field(primary_key=True, foreign_key="purpose.id")
    summary: str = Field(nullable=False, max_length=5000)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
