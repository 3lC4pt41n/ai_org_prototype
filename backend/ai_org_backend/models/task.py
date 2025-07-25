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
    assignee: Optional[str] = Field(default=None, max_length=100)
    
    # Additional fields
    notes: str = Field(default="", max_length=5000)
    tags: Optional[str] = Field(default=None, max_length=500)  # comma-separated
    estimated_hours: Optional[float] = Field(default=None, ge=0.0)
    actual_hours: Optional[float] = Field(default=None, ge=0.0)
    
    # Timestamps
    created_at: dt = Field(default_factory=dt.utcnow, nullable=False)
    updated_at: Optional[dt] = Field(default=None)
    started_at: Optional[dt] = Field(default=None)
    completed_at: Optional[dt] = Field(default=None)
    due_date: Optional[dt] = Field(default=None)

    # Activity tracking
    is_active: bool = Field(default=True)
    cost_estimate: Optional[float] = Field(default=None, ge=0.0)
    actual_cost: Optional[float] = Field(default=None, ge=0.0)

    # SQLModel-Style Relationships
    tenant: "Tenant" = Relationship(
        back_populates="tasks",
        sa_relationship_kwargs={"foreign_keys": "[Task.tenant_id]"}
    )

    purpose: Optional["Purpose"] = Relationship(
        back_populates="tasks",
        sa_relationship_kwargs={"foreign_keys": "[Task.purpose_id]"}
    )

    # Dependencies - renamed for clarity
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
        sa_relationship_kwargs={
            "foreign_keys": "[Artifact.task_id]",
            "cascade": "all, delete-orphan"
        }
    )

    def __str__(self) -> str:
        title_part = f": {self.title}" if self.title else ""
        return f"Task({self.id}{title_part})"

    def __repr__(self) -> str:
        return f"Task(id='{self.id}', status='{self.status}', description='{self.description[:50]}...')"

    @property
    def is_completed(self) -> bool:
        """Check if task is completed."""
        return self.status == TaskStatus.DONE

    @property
    def is_blocked(self) -> bool:
        """Check if task is blocked."""
        return self.status == TaskStatus.BLOCKED

    @property
    def is_overdue(self) -> bool:
        """Check if task is overdue."""
        if not self.due_date or self.is_completed:
            return False
        return dt.utcnow() > self.due_date

    @property
    def token_efficiency(self) -> Optional[float]:
        """Calculate token efficiency (actual vs planned)."""
        if self.tokens_plan == 0:
            return None
        return self.tokens_actual / self.tokens_plan

    @property
    def hours_efficiency(self) -> Optional[float]:
        """Calculate hours efficiency (actual vs estimated)."""
        if not self.estimated_hours or self.estimated_hours == 0:
            return None
        if not self.actual_hours:
            return None
        return self.actual_hours / self.estimated_hours

    @property
    def dependency_count(self) -> dict:
        """Get dependency counts."""
        return {
            "outgoing": len(self.outgoing_dependencies) if self.outgoing_dependencies else 0,
            "incoming": len(self.incoming_dependencies) if self.incoming_dependencies else 0
        }

    def start_work(self) -> None:
        """Mark task as started."""
        if self.status == TaskStatus.TODO:
            self.status = TaskStatus.DOING
            self.started_at = dt.utcnow()
            self.updated_at = dt.utcnow()

    def complete_task(self) -> None:
        """Mark task as completed."""
        if self.status in [TaskStatus.TODO, TaskStatus.DOING]:
            self.status = TaskStatus.DONE
            self.completed_at = dt.utcnow()
            self.updated_at = dt.utcnow()

    def block_task(self, reason: Optional[str] = None) -> None:
        """Mark task as blocked."""
        if self.status in [TaskStatus.TODO, TaskStatus.DOING]:
            self.status = TaskStatus.BLOCKED
            if reason:
                self.notes = f"{self.notes}\n[BLOCKED] {reason}".strip()
            self.updated_at = dt.utcnow()

    def unblock_task(self) -> None:
        """Remove blocked status."""
        if self.status == TaskStatus.BLOCKED:
            self.status = TaskStatus.TODO
            self.updated_at = dt.utcnow()

    def cancel_task(self, reason: Optional[str] = None) -> None:
        """Cancel the task."""
        self.status = TaskStatus.CANCELLED
        if reason:
            self.notes = f"{self.notes}\n[CANCELLED] {reason}".strip()
        self.updated_at = dt.utcnow()

    def update_progress(
        self, 
        actual_tokens: Optional[int] = None,
        actual_hours: Optional[float] = None,
        notes_update: Optional[str] = None
    ) -> None:
        """Update task progress."""
        if actual_tokens is not None:
            self.tokens_actual = actual_tokens
        if actual_hours is not None:
            self.actual_hours = actual_hours
        if notes_update:
            self.notes = f"{self.notes}\n{dt.utcnow().isoformat()}: {notes_update}".strip()
        self.updated_at = dt.utcnow()

    def add_tag(self, tag: str) -> None:
        """Add a tag to the task."""
        if not self.tags:
            self.tags = tag
        else:
            existing_tags = set(self.tags.split(","))
            existing_tags.add(tag.strip())
            self.tags = ",".join(sorted(existing_tags))
        self.updated_at = dt.utcnow()

    def remove_tag(self, tag: str) -> None:
        """Remove a tag from the task."""
        if not self.tags:
            return
        existing_tags = set(self.tags.split(","))
        existing_tags.discard(tag.strip())
        self.tags = ",".join(sorted(existing_tags)) if existing_tags else None
        self.updated_at = dt.utcnow()

    @property
    def tag_list(self) -> List[str]:
        """Get tags as a list."""
        if not self.tags:
            return []
        return [tag.strip() for tag in self.tags.split(",") if tag.strip()]

    @classmethod
    def create_with_validation(
        cls,
        tenant_id: str,
        description: str,
        title: Optional[str] = None,
        purpose_id: Optional[str] = None,
        business_value: float = 1.0,
        priority: TaskPriority = TaskPriority.MEDIUM,
        owner: Optional[str] = None,
        due_date: Optional[dt] = None
    ) -> "Task":
        """Create a new task with validation."""
        if not description or not description.strip():
            raise ValueError("Task description cannot be empty")
        
        if
