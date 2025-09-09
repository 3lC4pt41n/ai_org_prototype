import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, SQLModel

if TYPE_CHECKING:  # pragma: no cover
    pass


class ChatRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    AGENT = "agent"


class ChatMessage(SQLModel, table=True):
    """Chat message in an interactive conversation."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8], primary_key=True)
    tenant_id: str = Field(foreign_key="tenant.id", nullable=False)
    purpose_id: Optional[str] = Field(default=None, foreign_key="purpose.id")
    artifact_id: Optional[str] = Field(default=None, foreign_key="artifact.id")
    task_id: Optional[str] = Field(default=None, foreign_key="task.id")
    role: ChatRole = Field(nullable=False)
    content: str = Field(nullable=False, max_length=5000)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
