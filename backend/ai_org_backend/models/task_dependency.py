from typing import TYPE_CHECKING, Optional
from sqlmodel import SQLModel, Field, Relationship

if TYPE_CHECKING:
    from .task import Task


class TaskDependency(SQLModel, table=True):
    """Dependency relationships between tasks."""

    id: Optional[int] = Field(default=None, primary_key=True)
    
    # CORRECTED: Use the original field names from the existing database
    from_id: str = Field(foreign_key="task.id", nullable=False)
    to_id: str = Field(foreign_key="task.id", nullable=False)
    
    # ADD: The missing dependency_type field (this requires DB migration)
    dependency_type: str = Field(max_length=50, nullable=False, default="blocks")
    
    from_task: "Task" = Relationship(
        back_populates="outgoing_dependencies",
        sa_relationship_kwargs={"foreign_keys": "[TaskDependency.from_id]"}
    )
    to_task: "Task" = Relationship(
        back_populates="incoming_dependencies",
        sa_relationship_kwargs={"foreign_keys": "[TaskDependency.to_id]"}
    )
