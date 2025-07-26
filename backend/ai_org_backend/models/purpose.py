from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlmodel import SQLModel, Field, Relationship

if TYPE_CHECKING:
    from .tenant import Tenant
    from .task import Task


class Purpose(SQLModel, table=True):
    """High level project purpose."""

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4())[:8], 
        primary_key=True
    )
    
    tenant_id: str = Field(foreign_key="tenant.id", nullable=False)
    name: str = Field(nullable=False, min_length=1, max_length=255)
    
    description: Optional[str] = Field(default=None)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: Optional[datetime] = Field(default=None)

    # FIXED: No List[] in the type annotation - SQLModel handles it internally
    tenant: "Tenant" = Relationship(back_populates="purposes")
    tasks: list["Task"] = Relationship(back_populates="purpose")
