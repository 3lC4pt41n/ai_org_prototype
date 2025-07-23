from __future__ import annotations

import uuid
from enum import Enum
from datetime import datetime as dt
from typing import Optional, TYPE_CHECKING, List
from sqlalchemy.orm import Mapped


from sqlmodel import SQLModel, Field, Relationship

if TYPE_CHECKING:
    from .tenant import Tenant
    from .purpose import Purpose
    from .artifact import Artifact
    from .task_dependency import TaskDependency


class DepKind(str, Enum):
    """Dependency type for tasks."""

    FINISH_START = "FS"
    START_START = "SS"
    FINISH_FINISH = "FF"
    START_FINISH = "SF"


class Task(SQLModel, table=True):
    """Core work item tracked in Neo4j + SQL."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8], primary_key=True)

    tenant_id: str = Field(foreign_key="tenant.id")
    tenant: "Tenant" = Relationship(back_populates="tasks")
    purpose_id: str | None = Field(default=None, foreign_key="purpose.id")
    purpose: "Purpose" = Relationship(back_populates="tasks")

    description: str
    business_value: float = 1.0
    tokens_plan: int = 0
    tokens_actual: int = 0
    purpose_relevance: float = 0.0
    status: str = "todo"
    owner: Optional[str] = None
    notes: str = ""

    # N:M edges only (see task_dependency.py)
    outgoing: Mapped[List["TaskDependency"]] = Relationship(
        back_populates="from_task",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    incoming: Mapped[List["TaskDependency"]] = Relationship(
        back_populates="to_task",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )

    created_at: dt = Field(default_factory=dt.utcnow)

    artefacts: Mapped[List["Artifact"]] = Relationship(back_populates="task")
