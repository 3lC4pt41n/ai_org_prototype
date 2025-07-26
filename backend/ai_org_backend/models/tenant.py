from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

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
    
    name: str = Field(nullable=False, min_length=1, max_length=255)
    balance: float = Field(default=settings.default_budget, ge=0.0)
    
    email: Optional[str] = Field(default=None)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: Optional[datetime] = Field(default=None)

    # FIXED: Use list["Model"] instead of List["Model"] - this is the key!
    tasks: list["Task"] = Relationship(back_populates="tenant")
    purposes: list["Purpose"] = Relationship(back_populates="tenant")
