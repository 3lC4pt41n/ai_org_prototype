from __future__ import annotations
import uuid
from datetime import datetime as dt
from typing import Optional, TYPE_CHECKING, List

import sqlalchemy as sa
from enum import Enum
from sqlmodel import SQLModel, Field
from sqlalchemy.orm import Mapped, relationship

from .task_dependency import TaskDependency
from .artifact import Artifact

if TYPE_CHECKING:  # verhindert Laufzeit‐Zyklus
    from .tenant import Tenant
    from .purpose import Purpose


class TaskStatus(str, Enum):
    """Status values for :class:`Task`."""

    TODO = "todo"
    DOING = "doing"
    DONE = "done"


class Task(SQLModel, table=True):
    """Core work item tracked in Neo4j + SQL."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8], primary_key=True)

    tenant_id: str = Field(foreign_key="tenant.id")
    tenant: Mapped["Tenant"] = relationship(
        "Tenant", back_populates="tasks", foreign_keys=[tenant_id]
    )

    purpose_id: str = Field(default=None, foreign_key="purpose.id")
    purpose: Mapped["Purpose"] = relationship(
        "Purpose", back_populates="tasks", foreign_keys=[purpose_id]
    )

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
    outgoing: Mapped[List["TaskDependency"]] = relationship(
        "TaskDependency",
        back_populates="from_task",
        foreign_keys=[TaskDependency.from_id],
        cascade="all, delete-orphan",
    )
    incoming: Mapped[List["TaskDependency"]] = relationship(
        "TaskDependency",
        back_populates="to_task",
        foreign_keys=[TaskDependency.to_id],
        cascade="all, delete-orphan",
    )

    created_at: dt = Field(default_factory=dt.utcnow)

    artifacts: Mapped[List["Artifact"]] = relationship(
        "Artifact", back_populates="task", foreign_keys=[Artifact.task_id]
    )
