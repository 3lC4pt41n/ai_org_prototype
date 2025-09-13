import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional

import sqlalchemy as sa
from pydantic import ConfigDict
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:  # pragma: no cover
    from .artifact import Artifact


class ChatRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    AGENT = "agent"

    def __str__(self) -> str:
        return self.value


class ChatScope(str, Enum):
    GLOBAL = "global"
    ARTIFACT = "artifact"
    MIXED = "mixed"

    def __str__(self) -> str:
        return self.value


class ChatIntent(str, Enum):
    QUESTION = "question"
    FEEDBACK = "feedback"
    NOTE = "note"
    APPROVAL = "approval"

    def __str__(self) -> str:
        return self.value


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
    role: ChatRole = Field(nullable=False)
    scope: ChatScope = Field(default=ChatScope.GLOBAL, nullable=False)
    intent: ChatIntent = Field(default=ChatIntent.QUESTION, nullable=False)
    content: str = Field(nullable=False, max_length=5000)
    metadata_: dict | None = Field(
        default=None, sa_column=sa.Column("metadata", sa.JSON), alias="metadata"
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
