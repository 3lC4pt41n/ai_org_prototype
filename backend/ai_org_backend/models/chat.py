import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, SQLModel
import sqlalchemy as sa
from pydantic import ConfigDict

if TYPE_CHECKING:  # pragma: no cover
    pass


class ChatRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    AGENT = "agent"


class ChatMessage(SQLModel, table=True):
    """Chat message in an interactive conversation."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8], primary_key=True)
    tenant_id: str = Field(foreign_key="tenant.id", nullable=False)
    purpose_id: Optional[str] = Field(default=None, foreign_key="purpose.id")
    artifact_id: Optional[str] = Field(default=None, foreign_key="artifact.id")
    task_id: Optional[str] = Field(default=None, foreign_key="task.id")
    role: ChatRole = Field(nullable=False)
    content: str = Field(nullable=False, max_length=5000)
    metadata_: dict | None = Field(
        default=None, sa_column=sa.Column("metadata", sa.JSON), alias="metadata"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)


class ChatThreadContext(SQLModel, table=True):
    """Summary context for chat threads."""

    purpose_id: str = Field(primary_key=True, foreign_key="purpose.id")
    summary: str = Field(nullable=False, max_length=5000)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
