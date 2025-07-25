from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, List
from sqlalchemy.orm import Mapped, relationship

from sqlmodel import SQLModel, Field

if TYPE_CHECKING:  # pragma: no cover - type hints
    from .tenant import Tenant
    from .task import Task


class Purpose(SQLModel, table=True):
    """High level project purpose."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8], primary_key=True)
    tenant_id: str = Field(foreign_key="tenant.id")
    name: str

    tenant: Mapped["Tenant"] = relationship(back_populates="purposes")
    tasks: Mapped[List["Task"]] = relationship(back_populates="purpose")

