import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from .feedback import Feedback
    from .pipeline import PipelineTemplate
    from .task import Task
    from .tenant import Tenant


class Purpose(SQLModel, table=True):  # type: ignore[call-arg]
    """High level project purpose."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8], primary_key=True)

    tenant_id: str = Field(foreign_key="tenant.id", nullable=False)
    name: str = Field(nullable=False, min_length=1, max_length=255)

    description: Optional[str] = Field(default=None)
    is_active: bool = Field(default=True)
    mode: str = Field(default="manual", nullable=False)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: Optional[datetime] = Field(default=None)
    pipeline_template_id: Optional[str] = Field(
        default=None, foreign_key="pipeline_template.id"
    )

    tenant: "Tenant" = Relationship(back_populates="purposes")
    tasks: List["Task"] = Relationship(back_populates="purpose")
    feedback: List["Feedback"] = Relationship(back_populates="purpose")
    pipeline_template: Optional["PipelineTemplate"] = Relationship(
        back_populates="purposes"
    )
