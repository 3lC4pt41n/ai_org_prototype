"""Pipeline template models defining configurable phase blueprints."""

import uuid
from datetime import datetime
from typing import List, Optional, TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:  # pragma: no cover - import for type checking only
    from .purpose import Purpose
    from .task import Task


class PipelineTemplate(SQLModel, table=True):  # type: ignore[call-arg]
    """A reusable ordered blueprint describing a pipeline of phases."""

    __tablename__ = "pipeline_template"

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8], primary_key=True)
    name: str = Field(nullable=False, max_length=255)
    description: Optional[str] = Field(default=None, max_length=2000)
    tenant_id: Optional[str] = Field(default=None, foreign_key="tenant.id")
    is_default: bool = Field(default=False, nullable=False)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: Optional[datetime] = Field(default=None)

    phases: List["PipelinePhase"] = Relationship(
        back_populates="template",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "order_by": "PipelinePhase.position",
        },
    )
    purposes: List["Purpose"] = Relationship(back_populates="pipeline_template")


class PipelinePhase(SQLModel, table=True):  # type: ignore[call-arg]
    """Single phase entry belonging to a :class:`PipelineTemplate`."""

    __tablename__ = "pipeline_phase"

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8], primary_key=True)
    pipeline_template_id: str = Field(foreign_key="pipeline_template.id", nullable=False)
    name: str = Field(nullable=False, max_length=255)
    position: int = Field(default=0, ge=0)
    predecessor_id: Optional[str] = Field(
        default=None, foreign_key="pipeline_phase.id", nullable=True
    )

    agent_role: Optional[str] = Field(default=None, max_length=100)
    prompt_template: Optional[str] = Field(default=None, max_length=255)
    model_name: Optional[str] = Field(default=None, max_length=255)
    tokens_plan_default: int = Field(default=0, ge=0)
    business_value_default: float = Field(default=1.0)
    purpose_relevance_default: float = Field(default=1.0)
    requires_approval: bool = Field(default=False, nullable=False)

    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: Optional[datetime] = Field(default=None)

    template: "PipelineTemplate" = Relationship(back_populates="phases")
    predecessor: Optional["PipelinePhase"] = Relationship(  # type: ignore[valid-type]
        back_populates="dependents",
        sa_relationship_kwargs={"remote_side": "PipelinePhase.id"},
    )
    dependents: List["PipelinePhase"] = Relationship(
        back_populates="predecessor",
        sa_relationship_kwargs={"cascade": "all"},
    )
    tasks: List["Task"] = Relationship(back_populates="pipeline_phase")

