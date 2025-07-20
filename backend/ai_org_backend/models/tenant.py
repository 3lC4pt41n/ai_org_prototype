from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, List

from sqlmodel import SQLModel, Field, Relationship

if TYPE_CHECKING:
    from .task import Task

class Tenant(SQLModel, table=True):
    """Simple tenant model (multi-tenant future-proofing)."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    name: str
    balance: float = 0.0

    tasks: List["Task"] = Relationship(back_populates="tenant")
