from typing import TYPE_CHECKING, Optional
from sqlmodel import SQLModel, Field, Relationship

if TYPE_CHECKING:
    from .task import Task


class TaskDependency(SQLModel, table=True):
    """Dependency relationships between tasks."""

    id: Optional[int] = Field(default=None, primary_key=True)
    
    # FIXED: Use the field names that seed_graph.py expects
    from_id: str = Field(foreign_key="task.id", nullable=False)
    to_id: str = Field(foreign_key="task.id", nullable=False)
    
    dependency_type: str = Field(max_length=50, nullable=False, default="blocks")
    
    # FIXED: Update the foreign_keys references to match the field names
    from_task: "Task" = Relationship(
        back_populates="outgoing_dependencies",
        sa_relationship_kwargs={"foreign_keys": "[TaskDependency.from_id]"}
    )
    to_task: "Task" = Relationship(
        back_populates="incoming_dependencies",
        sa_relationship_kwargs={"foreign_keys": "[TaskDependency.to_id]"}
    )

    def __str__(self) -> str:
        return f"TaskDependency({self.from_id} -> {self.to_id})"
