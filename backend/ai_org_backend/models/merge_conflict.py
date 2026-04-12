"""S5-B2: Merge Conflict model.

Records unresolvable file conflicts detected during automatic merge of
parallel Dev-Agent outputs.  Unresolved conflicts generate a
MANUAL_MERGE_TASK for human intervention.
"""

import uuid
from datetime import datetime as dt
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


class MergeConflictStatus(str, Enum):
    OPEN = "open"
    RESOLVED_AUTO = "resolved_auto"
    RESOLVED_MANUAL = "resolved_manual"


class MergeConflict(SQLModel, table=True):  # type: ignore[call-arg]
    """A merge conflict between two task outputs."""

    __tablename__ = "merge_conflict"

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4())[:8],
        primary_key=True,
    )
    purpose_id: str = Field(foreign_key="purpose.id", nullable=False)
    tenant_id: str = Field(foreign_key="tenant.id", nullable=False)

    # The two tasks whose outputs conflict
    task_a_id: str = Field(foreign_key="task.id", nullable=False)
    task_b_id: str = Field(foreign_key="task.id", nullable=False)

    file_path: str = Field(nullable=False, max_length=500)
    conflict_type: str = Field(default="content_overlap", max_length=50)
    description: Optional[str] = Field(default=None)

    status: str = Field(default=MergeConflictStatus.OPEN)
    resolution_task_id: Optional[str] = Field(default=None, foreign_key="task.id")

    created_at: dt = Field(default_factory=dt.utcnow, nullable=False)
    resolved_at: Optional[dt] = Field(default=None)
