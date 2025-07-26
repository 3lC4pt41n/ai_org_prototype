from __future__ import annotations

import uuid
from datetime import datetime as dt
from typing import Optional, TYPE_CHECKING, List
from enum import Enum

from sqlmodel import SQLModel, Field, Relationship

if TYPE_CHECKING:
    from .tenant import Tenant
    from .purpose import Purpose
    from .task_dependency import TaskDependency
    from .artifact import Artifact


class TaskStatus(str, Enum):
    """Status values for :class:`Task`."""

    TODO = "todo"
    DOING = "doing"
    DONE = "done"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class TaskPriority(str, Enum):
    """Priority levels for tasks."""
    
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class Task(SQLModel, table=True):
    """Core work item tracked in SQL."""

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4())[:8], 
        primary_key=True,
        min_length=8,
        max_length=8
    )

    # Foreign Keys
    tenant_id: str = Field(foreign_key="tenant.id", nullable=False)
    purpose_id: Optional[str] = Field(default=None, foreign_key="purpose.id")

    # Core fields
    description: str = Field(nullable=False, min_length=1, max_length=2000)
    title: Optional[str] = Field(default=None, max_length=200)
    
    # Business metrics
    business_value: float = Field(default=1.0, ge=0.0, le=10.0)
    tokens_plan: int = Field(default=0, ge=0)
    tokens_actual: int = Field(default=0, ge=0)
    purpose_relevance: float = Field(default=0.0, ge=0.0, le=1.0)
    
    # Status and workflow
    status: TaskStatus = Field(default=TaskStatus.TODO)
    priority: TaskPriority = Field(default=TaskPriority.MEDIUM)
    owner: Optional[str] = Field(default=None, max_length=100)
    
    # Additional fields
    notes: str = Field(default="", max_length=5000)
    
    # Timestamps
    created_at: dt = Field(default_factory=dt.utcnow, nullable=False)
    updated_at: Optional[dt] = Field(default=None)

    # FIXED: Proper SQLModel Relationships - NO Mapped[], just direct types
    tenant: "Tenant" = Relationship(back_populates="tasks")
    purpose: Optional["Purpose"] = Relationship(back_populates="tasks")

    # Dependencies - proper relationship names
    outgoing_dependencies: List["TaskDependency"] = Relationship(
        back_populates="from_task",
        sa_relationship_kwargs={
            "foreign_keys": "[TaskDependency.from_task_id]",
            "cascade": "all, delete-orphan"
        }
    )
    
    incoming_dependencies: List["TaskDependency"] = Relationship(
        back_populates="to_task",
        sa_relationship_kwargs={
            "foreign_keys": "[TaskDependency.to_task_id]",
            "cascade": "all, delete-orphan"
        }
    )

    artifacts: List["Artifact"] = Relationship(
        back_populates="task",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )

    def __str__(self) -> str:
        title_part = f": {self.title}" if self.title else ""
        return f"Task({self.id}{title_part})"

    @property
    def is_completed(self) -> bool:
        """Check if task is completed."""
        return self.status == TaskStatus.DONE
