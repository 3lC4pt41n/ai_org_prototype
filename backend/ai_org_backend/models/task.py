import uuid
from datetime import datetime as dt
from typing import Optional, TYPE_CHECKING, List
from enum import Enum

from sqlmodel import SQLModel, Field, Relationship

if TYPE_CHECKING:
    from .tenant import Tenant
    from .purpose import Purpose
    from .task_dependency import TaskDependency
    from .artifact import Artifact
    from .pipeline import PipelinePhase


class TaskStatus(str, Enum):
    """Status values for :class:`Task`."""

    TODO = "todo"
    DOING = "doing"
    DONE = "done"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    # Mark task skipped (no artefact or prerequisites)
    SKIPPED = "skipped"
    # Mark task skipped due to insufficient budget
    BUDGET_EXCEEDED = "budget_exceeded"
    # S2-05: Task moved to dead-letter queue after exhausting retries
    DEAD_LETTER = "dead_letter"
    # Task failed permanently
    FAILED = "failed"


class TaskOwner(str, Enum):
    """Normalized owner identifiers used across agents and orchestrators."""

    ARCHITECT = "ARCHITECT"
    DEV = "DEV"
    INSIGHT = "INSIGHT"
    PM = "PM"
    PRODUCT_OWNER = "PRODUCT_OWNER"
    QA = "QA"
    QA_E2E = "QA_E2E"
    QA_INTEGRATION = "QA_INTEGRATION"
    QA_PERF = "QA_PERF"
    QA_REFACTOR = "QA_REFACTOR"
    QA_REVIEW = "QA_REVIEW"
    QA_SECURITY = "QA_SECURITY"
    REPO = "REPO"
    REVIEW = "REVIEW"
    TELEMETRY = "TELEMETRY"
    UX_UI = "UX_UI"
    VISION_AGENT = "VISION_AGENT"


class Task(SQLModel, table=True):  # type: ignore[call-arg]
    """Core work item tracked in SQL.

    Notes on CASCADE DELETE: The tenant_id and purpose_id foreign keys include
    ON DELETE CASCADE constraints, enforced at the database level via migration
    20260329_s1_cascade_and_constraints. When a Tenant or Purpose is deleted,
    all related Tasks are automatically deleted.
    """

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4())[:8],
        primary_key=True
    )

    # Foreign Keys
    tenant_id: str = Field(
        foreign_key="tenant.id",
        nullable=False,
        description="Tenant ID (CASCADE DELETE)"
    )
    purpose_id: Optional[str] = Field(
        default=None,
        foreign_key="purpose.id",
        description="Purpose ID (CASCADE DELETE)"
    )
    pipeline_phase_id: Optional[str] = Field(
        default=None, foreign_key="pipeline_phase.id"
    )

    # Core fields
    description: str = Field(nullable=False, min_length=1, max_length=2000)
    business_value: float = Field(default=1.0, ge=0.0, le=10.0)
    tokens_plan: int = Field(default=0, ge=0)
    tokens_actual: int = Field(default=0, ge=0)
    purpose_relevance: float = Field(default=0.0, ge=0.0, le=1.0)
    agent_role: Optional[str] = Field(default=None, max_length=100)
    model_name: Optional[str] = Field(default=None, max_length=255)
    prompt_template: Optional[str] = Field(default=None, max_length=255)
    requires_approval: bool = Field(default=False, nullable=False)
    
    # Status and workflow
    status: str = Field(default="todo")
    owner: Optional[str] = Field(default=None)
    notes: str = Field(default="")
    # ───────────── Retry support ─────────────
    # how often this task wurde bereits automatisch erneut versucht
    retries: int = Field(default=0, ge=0)

    issues_found: int = Field(default=0, ge=0)

    # S2-03: Optimistic locking version counter – incremented on every status
    # change via ``cas_update_status()``.  Concurrent writers that read the
    # same version will fail with ``StaleTaskError``.
    version: int = Field(default=0, ge=0)

    # S5-B1: Code review status tracking
    code_review_status: Optional[str] = Field(
        default=None, max_length=30,
        description="reviewing | changes_requested | approved | requires_manual_review",
    )
    # S5-B3: Review round counter (prevents infinite re-review loops)
    review_rounds: int = Field(default=0, ge=0)

    # S2-04 / S2-06: Timestamp of last activity (heartbeat or status change)
    # for stuck-task detection.  Updated whenever the task transitions or a
    # worker sends a heartbeat.
    last_heartbeat_at: Optional[dt] = Field(default=None)
    
    # Timestamps
    created_at: dt = Field(default_factory=dt.utcnow, nullable=False)

    # Relationships
    tenant: "Tenant" = Relationship(back_populates="tasks")
    purpose: Optional["Purpose"] = Relationship(back_populates="tasks")
    pipeline_phase: Optional["PipelinePhase"] = Relationship(
        back_populates="tasks"
    )

    # CORRECTED: Use the correct field names that match TaskDependency
    outgoing_dependencies: List["TaskDependency"] = Relationship(
        back_populates="from_task",
        sa_relationship_kwargs={
            "foreign_keys": "[TaskDependency.from_id]",  # Corrected to from_id
            "cascade": "all, delete-orphan"
        }
    )
    
    incoming_dependencies: List["TaskDependency"] = Relationship(
        back_populates="to_task",
        sa_relationship_kwargs={
            "foreign_keys": "[TaskDependency.to_id]",  # Corrected to to_id
            "cascade": "all, delete-orphan"
        }
    )

    artifacts: List["Artifact"] = Relationship(
        back_populates="task",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )

    @property
    def is_completed(self) -> bool:
        return self.status == TaskStatus.DONE
