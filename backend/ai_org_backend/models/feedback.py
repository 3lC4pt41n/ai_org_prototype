import uuid
from datetime import datetime
from typing import Optional
from enum import Enum

from sqlmodel import SQLModel, Field, Relationship


class FeedbackType(str, Enum):
    PRD = "prd"
    BLUEPRINT = "blueprint"


class Feedback(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8], primary_key=True)

    tenant_id: str = Field(foreign_key="tenant.id", nullable=False)
    purpose_id: str = Field(foreign_key="purpose.id", nullable=False)
    type: FeedbackType = Field(nullable=False)
    version: int = Field(default=1, ge=1)
    text: str = Field(default="")
    approved: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)

    # Relationships
    purpose: Optional["Purpose"] = Relationship(back_populates="feedback")


# Avoid circular imports for type checking
if False:  # pragma: no cover
    from .purpose import Purpose
