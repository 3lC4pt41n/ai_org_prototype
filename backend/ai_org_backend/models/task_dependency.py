from typing import TYPE_CHECKING, Optional
from sqlmodel import SQLModel, Field, Relationship

if TYPE_CHECKING:
    from .task import Task


class TaskDependency(SQLModel, table=True):  # type: ignore[call-arg]
    """Dependency relationships between tasks.

    Notes on CASCADE DELETE: Foreign key constraints include ON DELETE CASCADE
    to automatically remove dependent records when a Task is deleted. This is
    enforced at the database level via migration 20260329_s1_cascade_and_constraints.
    """

    __tablename__ = "task_dependency"

    id: Optional[int] = Field(default=None, primary_key=True)

    from_id: str = Field(
        foreign_key="task.id",
        nullable=False,
        description="ID of the task this dependency originates from (CASCADE DELETE)"
    )
    to_id: str = Field(
        foreign_key="task.id",
        nullable=False,
        description="ID of the task this dependency points to (CASCADE DELETE)"
    )

    # dependency_type field with server default 'blocks' and CHECK constraint
    # Enforced at DB level via migration 20260329_s1_cascade_and_constraints
    dependency_type: str = Field(
        max_length=50,
        nullable=False,
        default="blocks",
        description="Type of dependency: 'blocks', 'FINISH_START', or 'depends_on'"
    )
    
    from_task: "Task" = Relationship(
        back_populates="outgoing_dependencies",
        sa_relationship_kwargs={"foreign_keys": "[TaskDependency.from_id]"}
    )
    to_task: "Task" = Relationship(
        back_populates="incoming_dependencies",
        sa_relationship_kwargs={"foreign_keys": "[TaskDependency.to_id]"}
    )
