"""Models for storing prompt templates and tenant assignments."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from sqlmodel import Field, Relationship, SQLModel

class PromptTemplate(SQLModel, table=True):  # type: ignore[call-arg]
    """A prompt template that can be customised per tenant or globally."""

    __tablename__ = "prompt_template"

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8], primary_key=True)
    phase_slug: str = Field(nullable=False, max_length=64, index=True)
    agent: Optional[str] = Field(default=None, max_length=100)
    default_path: Optional[str] = Field(default=None, max_length=255)
    created_by: Optional[str] = Field(default=None, max_length=255)
    content: str = Field(nullable=False)
    tenant_id: Optional[str] = Field(default=None, foreign_key="tenant.id")
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: Optional[datetime] = Field(default=None)

    assignments: List["TenantPromptAssignment"] = Relationship(
        back_populates="prompt_template",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class TenantPromptAssignment(SQLModel, table=True):  # type: ignore[call-arg]
    """Mapping of tenant/phase pairs to the prompt template used by default."""

    __tablename__ = "tenant_prompt_assignment"

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8], primary_key=True)
    tenant_id: str = Field(foreign_key="tenant.id", nullable=False)
    phase_slug: str = Field(nullable=False, max_length=64)
    prompt_template_id: str = Field(foreign_key="prompt_template.id", nullable=False)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)

    prompt_template: PromptTemplate = Relationship(back_populates="assignments")
