from __future__ import annotations
import uuid
from datetime import datetime as dt
from typing import Optional, TYPE_CHECKING, List

import sqlalchemy as sa
from enum import Enum
from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy.orm import Mapped

if TYPE_CHECKING:                # verhindert Laufzeit‐Zyklus
    from .tenant import Tenant
    from .purpose import Purpose
    from .artifact import Artifact
    from .task_dependency import TaskDependency


class TaskStatus(str, Enum):
    """Status values for :class:`Task`."""

    TODO = "todo"
    DOING = "doing"
    DONE = "done"


class Task(SQLModel, table=True):
    """Core work item tracked in Neo4j + SQL."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8], primary_key=True)

    tenant_id: str = Field(foreign_key="tenant.id")
    tenant: Mapped["Tenant"] = Relationship(back_populates="tasks")

    purpose_id: Optional[str] = Field(default=None, foreign_key="purpose.id")
    purpose: Mapped[Optional["Purpose"]] = Relationship(back_populates="tasks")

    description: str
    business_value: float = 1.0
    tokens_plan: int = 0
    tokens_actual: int = 0
    purpose_relevance: float = 0.0
    status: TaskStatus = Field(
        default=TaskStatus.TODO,
        sa_column=sa.Column(sa.Enum(TaskStatus), nullable=False),
    )
    owner: Optional[str] = None
    notes: str = ""

    # N:M edges (TaskDependency)
    outgoing: Mapped[List["TaskDependency"]] = Relationship(
        back_populates="from_task",
        sa_relationship_kwargs={
            "foreign_keys": "TaskDependency.from_id",
            "cascade": "all, delete-orphan",
        },
    )
    incoming: Mapped[List["TaskDependency"]] = Relationship(
        back_populates="to_task",
        sa_relationship_kwargs={
            "foreign_keys": "TaskDependency.to_id",
            "cascade": "all, delete-orphan",
        },
    )

    created_at: dt = Field(default_factory=dt.utcnow)

    artifacts: Mapped[List["Artifact"]] = Relationship(back_populates="task")
