from __future__ import annotations

import uuid
from typing import Optional, TYPE_CHECKING

from sqlmodel import SQLModel, Field, Relationship

from .task import DepKind

if TYPE_CHECKING:
    from .task import Task


class TaskDependency(SQLModel, table=True):
    """Join table for task dependencies."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8], primary_key=True)
    from_id: str = Field(foreign_key="task.id")
    to_id: str = Field(foreign_key="task.id")
    kind: DepKind = Field(default=DepKind.FINISH_START)
    source: Optional[str] = None
    note: Optional[str] = None

    from_task: "Task" = Relationship(
        sa_relationship_kwargs={"foreign_keys": "TaskDependency.from_id"},
        back_populates="prerequisites",
    )
    to_task: "Task" = Relationship(
        sa_relationship_kwargs={"foreign_keys": "TaskDependency.to_id"},
        back_populates="blocked_by",
    )
