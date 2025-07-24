from __future__ import annotations
from enum import Enum
from typing import Optional, TYPE_CHECKING

import sqlalchemy as sa
from sqlmodel import SQLModel, Field
from sqlalchemy.orm import Mapped, relationship

if TYPE_CHECKING:
    from .task import Task


class DepKind(str, Enum):
    FINISH_START = "FINISH_START"
    START_START = "START_START"
    FINISH_FINISH = "FINISH_FINISH"
    START_FINISH = "START_FINISH"


class TaskDependency(SQLModel, table=True):
    id: str = Field(default_factory=str, primary_key=True)

    from_id: str = Field(foreign_key="task.id")
    to_id: str = Field(foreign_key="task.id")

    kind: DepKind = Field(
        sa_column=sa.Column(sa.Enum(DepKind), nullable=False)
    )
    source: Optional[str] = None
    note: Optional[str] = None

    # Rückverweise
    from_task: Mapped["Task"] = relationship(
        back_populates="dependencies",
        foreign_keys=[from_id]
    )
    to_task: Mapped["Task"] = relationship(
        back_populates="dependents",
        foreign_keys=[to_id]
    )
