import uuid
from datetime import datetime
from typing import Optional

from sqlmodel import SQLModel, Field, Relationship


class ArtifactFeedback(SQLModel, table=True):
    """Feedback entries for a specific artifact.

    Each new submission for an artifact increments the version counter.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8], primary_key=True)
    artifact_id: str = Field(foreign_key="artifact.id", nullable=False)
    tenant_id: str = Field(foreign_key="tenant.id", nullable=False)
    author: Optional[str] = Field(default=None, nullable=True)
    version: int = Field(default=1, ge=1)
    content: str = Field(nullable=False)
    approved: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)

    artifact: Optional["Artifact"] = Relationship(back_populates="feedback")


# Avoid circular import for type checking
if False:  # pragma: no cover
    from .artifact import Artifact
