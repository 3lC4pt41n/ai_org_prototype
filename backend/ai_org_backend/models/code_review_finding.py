"""S5-B4: Code Review Finding model.

Persists structured findings from the Code-Review-Agent for analytics,
pattern detection, compliance reporting, and re-review tracking.
"""

import uuid
from datetime import datetime as dt
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


class FindingSeverity(str, Enum):
    """Severity levels for code review findings."""
    CRITICAL = "critical"    # Must fix before merge
    HIGH = "high"            # Should fix, blocks unless overridden
    MEDIUM = "medium"        # Advisory, nice to fix
    LOW = "low"              # Informational, log only


class FindingCategory(str, Enum):
    """Categories of code review findings."""
    SECURITY = "security"
    PERFORMANCE = "performance"
    CORRECTNESS = "correctness"
    STYLE = "style"
    ARCHITECTURE = "architecture"
    TESTING = "testing"
    DEPENDENCY = "dependency"
    NAMING = "naming"
    ERROR_HANDLING = "error_handling"
    OTHER = "other"


class CodeReviewFinding(SQLModel, table=True):  # type: ignore[call-arg]
    """A single code-review finding persisted to the database.

    Each finding references the review task, the purpose, and optionally
    the file/line where the issue was detected.  When a fix task resolves
    the finding, ``fixed`` is set to True and ``fix_task_id`` links to
    the remediation task.
    """

    __tablename__ = "code_review_finding"

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4())[:8],
        primary_key=True,
    )

    # Context
    task_id: str = Field(foreign_key="task.id", nullable=False)
    purpose_id: str = Field(foreign_key="purpose.id", nullable=False)
    tenant_id: str = Field(foreign_key="tenant.id", nullable=False)

    # Finding details
    severity: str = Field(nullable=False, max_length=20)
    category: str = Field(default="other", max_length=30)
    description: str = Field(nullable=False)
    file_path: Optional[str] = Field(default=None, max_length=500)
    line_number: Optional[int] = Field(default=None, ge=0)
    suggested_fix: Optional[str] = Field(default=None)
    code_snippet: Optional[str] = Field(default=None)

    # Resolution tracking
    fixed: bool = Field(default=False)
    fix_task_id: Optional[str] = Field(default=None, foreign_key="task.id")
    fix_commit_id: Optional[str] = Field(default=None, max_length=64)

    # Timestamps
    created_at: dt = Field(default_factory=dt.utcnow, nullable=False)
    resolved_at: Optional[dt] = Field(default=None)
