from __future__ import annotations
from enum import Enum
from typing import Optional, TYPE_CHECKING

import sqlalchemy as sa
from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy.orm import Mapped

if TYPE_CHECKING:
    from .task import Task


class DepKind(str, Enum):
    """Dependency type for tasks (short codes)."""
    FINISH_START = "FS"
    START_START = "SS"
    FINISH_FINISH = "FF"
    START_FINISH = "SF"


class TaskDependency(SQLModel, table=True):
    id: str = Field(default_factory=str, primary_key=True)

    from_id: str = Field(foreign_key="task.id")
    to_id: str = Field(foreign_key="task.id")

    kind: DepKind = Field(sa_column=sa.Column(sa.Enum(DepKind), nullable=False))
    source: Optional[str] = None
    note: Optional[str] = None

    from_task: Mapped["Task"] = Relationship(
        back_populates="outgoing",
        sa_relationship_kwargs={"foreign_keys": [from_id]},
    )
    to_task: Mapped["Task"] = Relationship(
        back_populates="incoming",
        sa_relationship_kwargs={"foreign_keys": [to_id]},
    )
