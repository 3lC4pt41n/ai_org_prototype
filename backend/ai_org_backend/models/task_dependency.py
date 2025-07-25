from __future__ import annotations
from enum import Enum
from typing import Optional, TYPE_CHECKING
import uuid

import sqlalchemy as sa
from sqlmodel import SQLModel, Field, Relationship
#from sqlalchemy.orm import Mapped, relationship

if TYPE_CHECKING:
    from .task import Task  # Verweis auf die Task-Klasse für Typüberprüfung

class TaskDependency(SQLModel, table=True):
    """Dependency type for tasks (short codes)."""
    
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Verwenden Sie String-References statt direkter Klassen-References
    from_task_id: int = Field(foreign_key="task.id", nullable=False)
    to_task_id: int = Field(foreign_key="task.id", nullable=False)
    
    dependency_type: str = Field(max_length=50, nullable=False)
    
    # Relationships mit back_populates
    from_task: "Task" = Relationship(
        back_populates="outgoing_dependencies",
        sa_relationship_kwargs={"foreign_keys": "[TaskDependency.from_task_id]"}
    )
    to_task: "Task" = Relationship(
        back_populates="incoming_dependencies", 
        sa_relationship_kwargs={"foreign_keys": "[TaskDependency.to_task_id]"}
    )
