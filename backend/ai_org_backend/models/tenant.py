from __future__ import annotations

import uuid
from typing import List
from sqlalchemy.orm import Mapped, relationship

from sqlmodel import SQLModel, Field
from ..settings import settings
from .task import Task
from .purpose import Purpose


class Tenant(SQLModel, table=True):
    """Simple tenant model (multi-tenant future-proofing)."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    name: str
    balance: float = settings.default_budget
    # ⇣ richtige Relationship-Syntax

    tasks: Mapped[List["Task"]] = relationship("Task", back_populates="tenant", foreign_keys=[Task.tenant_id])
    purposes: Mapped[List["Purpose"]] = relationship("Purpose", back_populates="tenant", foreign_keys=[Purpose.tenant_id])
