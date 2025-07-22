from __future__ import annotations

import uuid
from datetime import datetime as dt
from typing import Optional, TYPE_CHECKING, List

from sqlmodel import SQLModel, Field, Relationship

if TYPE_CHECKING:
    from .tenant import Tenant
    from .artifact import Artifact


class Task(SQLModel, table=True):
    """Core work item tracked in Neo4j + SQL."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8], primary_key=True)

    tenant_id: str = Field(foreign_key="tenant.id")
    tenant: "Tenant" = Relationship(back_populates="tasks")

    description: str
    business_value: float = 1.0
    tokens_plan: int = 0
    tokens_actual: int = 0
    purpose_relevance: float = 0.0
    status: str = "todo"
    owner: Optional[str] = None
    notes: str = ""

    depends_on: Optional[str] = Field(
        default=None,
        foreign_key="task.id",
        description="predecessor task id",
    )

    created_at: dt = Field(default_factory=dt.utcnow)

    artefacts: List["Artifact"] = Relationship(back_populates="task")
