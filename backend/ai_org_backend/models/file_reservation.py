"""S-Sprint4 Fix #8: File-Ownership Reservation Model.

Tracks which task has claimed ownership of which files within a purpose,
preventing multiple agents from writing to the same files simultaneously.
"""

from __future__ import annotations

import uuid
from datetime import datetime as dt
from typing import Optional

from sqlmodel import SQLModel, Field


class FileReservation(SQLModel, table=True):  # type: ignore[call-arg]
    """Tracks file ownership claims per task within a purpose."""

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        primary_key=True,
    )
    task_id: str = Field(nullable=False, foreign_key="task.id", index=True)
    purpose_id: str = Field(nullable=False, foreign_key="purpose.id", index=True)
    file_path: str = Field(nullable=False, max_length=500)
    created_at: dt = Field(default_factory=dt.utcnow, nullable=False)

    class Config:
        # Unique constraint: one task owns a file path within a purpose
        table_args = {"UniqueConstraint": ("file_path", "purpose_id", "task_id")}
