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
    # Mark task skipped (no artefact or prerequisites)
    SKIPPED = "skipped"
    # Mark task skipped due to insufficient budget
    BUDGET_EXCEEDED = "budget_exceeded"


class Task(SQLModel, table=True):
    """Core work item tracked in SQL."""

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4())[:8], 
        primary_key=True
    )

    # Foreign Keys
    tenant_id: str = Field(foreign_key="tenant.id", nullable=False)
    purpose_id: Optional[str] = Field(default=None, foreign_key="purpose.id")

    # Core fields
    description: str = Field(nullable=False, min_length=1, max_length=2000)
    business_value: float = Field(default=1.0, ge=0.0, le=10.0)
    tokens_plan: int = Field(default=0, ge=0)
    tokens_actual: int = Field(default=0, ge=0)
    purpose_relevance: float = Field(default=0.0, ge=0.0, le=1.0)
    
    # Status and workflow
    status: str = Field(default="todo")
    owner: Optional[str] = Field(default=None)
    notes: str = Field(default="")
    # ───────────── Retry support ─────────────
    # how often this task wurde bereits automatisch erneut versucht
    retries: int = Field(default=0, ge=0)
    
    # Timestamps
    created_at: dt = Field(default_factory=dt.utcnow, nullable=False)

    # Relationships
    tenant: "Tenant" = Relationship(back_populates="tasks")
    purpose: Optional["Purpose"] = Relationship(back_populates="tasks")

    # CORRECTED: Use the correct field names that match TaskDependency
    outgoing_dependencies: List["TaskDependency"] = Relationship(
        back_populates="from_task",
        sa_relationship_kwargs={
            "foreign_keys": "[TaskDependency.from_id]",  # Corrected to from_id
            "cascade": "all, delete-orphan"
        }
    )
    
    incoming_dependencies: List["TaskDependency"] = Relationship(
        back_populates="to_task",
        sa_relationship_kwargs={
            "foreign_keys": "[TaskDependency.to_id]",  # Corrected to to_id
            "cascade": "all, delete-orphan"
        }
    )

    artifacts: List["Artifact"] = Relationship(
        back_populates="task",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )

    @property
    def is_completed(self) -> bool:
        return self.status == TaskStatus.DONE
