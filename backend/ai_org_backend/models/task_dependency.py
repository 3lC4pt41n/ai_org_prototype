from __future__ import annotations
from enum import Enum
from typing import Optional, TYPE_CHECKING
import uuid

import sqlalchemy as sa
from sqlmodel import SQLModel, Field
from sqlalchemy.orm import Mapped, relationship

if TYPE_CHECKING:
    from .task import Task  # Verweis auf die Task-Klasse für Typüberprüfung

class DepKind(str, Enum):
    """Dependency type for tasks (short codes)."""
    FINISH_START = "FS"
    START_START = "SS"
    FINISH_FINISH = "FF"
    START_FINISH = "SF"

class TaskDependency(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    from_id: str = Field(foreign_key="task.id", nullable=False)
    to_id: str = Field(foreign_key="task.id", nullable=False)
    kind: DepKind = Field(sa_column=sa.Column(sa.Enum(DepKind), nullable=False))
    source: Optional[str] = Field(default=None, nullable=True)
    note: Optional[str] = Field(default=None, nullable=True)

    # Beziehungen zu Task (angenommen Task hat .outgoing und .incoming Listen definiert)
    from_task: Mapped["Task"] = relationship("Task", back_populates="outgoing", foreign_keys=[from_id])
    to_task: Mapped["Task"] = relationship("Task", back_populates="incoming", foreign_keys=[to_id])
