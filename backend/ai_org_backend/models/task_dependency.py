from __future__ import annotations
from enum import Enum
from typing import Optional, TYPE_CHECKING

import sqlalchemy as sa
from sqlmodel import SQLModel, Field
from sqlalchemy.orm import Mapped, relationship

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
    source: str = Field(default=None, nullable=True)
    note: str = Field(default=None, nullable=True)

    from_task: Mapped["Task"] = relationship("Task", back_populates="outgoing", foreign_keys=[from_id])
    to_task: Mapped["Task"] = relationship("Task", back_populates="incoming", foreign_keys=[to_id])
