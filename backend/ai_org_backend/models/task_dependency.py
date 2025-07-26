from __future__ import annotations

from typing import TYPE_CHECKING, Optional
from sqlmodel import SQLModel, Field, Relationship

if TYPE_CHECKING:
    from .task import Task


class TaskDependency(SQLModel, table=True):
    """Dependency relationships between tasks."""

    id: Optional[int] = Field(default=None, primary_key=True)
    
    # FIXED: Use str for UUID foreign keys, not int
    from_task_id: str = Field(foreign_key="task.id", nullable=False)
    to_task_id: str = Field(foreign_key="task.id", nullable=False)
    
    dependency_type: str = Field(max_length=50, nullable=False, default="blocks")
    
    # Relationships with proper back_populates
    from_task: "Task" = Relationship(
        back_populates="outgoing_dependencies",
        sa_relationship_kwargs={"foreign_keys": "[TaskDependency.from_task_id]"}
    )
    to_task: "Task" = Relationship(
        back_populates="incoming_dependencies",
        sa_relationship_kwargs={"foreign_keys": "[TaskDependency.to_task_id]"}
    )

    def __str__(self) -> str:
        return f"TaskDependency({self.from_task_id} -> {self.to_task_id})"
