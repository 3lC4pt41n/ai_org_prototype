from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlmodel import SQLModel, Field, Relationship

from ..settings import settings

if TYPE_CHECKING:
    from .task import Task
    from .purpose import Purpose


class Tenant(SQLModel, table=True):
    """Simple tenant model (multi-tenant future-proofing)."""

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), 
        primary_key=True
    )
    
    name: str = Field(nullable=False, min_length=1, max_length=255, unique=True)
    balance: float = Field(default=settings.default_budget, ge=0.0)
    
    email: Optional[str] = Field(default=None, max_length=255)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: Optional[datetime] = Field(default=None)

    # FIXED: Proper SQLModel Relationships - NO Mapped[], just direct List[]
    tasks: List["Task"] = Relationship(back_populates="tenant")
    purposes: List["Purpose"] = Relationship(back_populates="tenant")

    def __str__(self) -> str:
        return f"Tenant({self.id}: {self.name})"
