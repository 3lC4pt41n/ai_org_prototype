import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, ClassVar, Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel
from sqlalchemy.orm import Mapped, relationship

from ..settings import settings

if TYPE_CHECKING:
    from .purpose import Purpose
    from .task import Task
    from .prompt_template import TenantPromptAssignment


class UserTheme(str, Enum):
    """Enum for UI theme preference (must match Postgres ENUM values)."""

    light = "light"
    dark = "dark"


class Tenant(SQLModel, table=True):  # type: ignore[call-arg]
    """Simple tenant model (multi-tenant future-proofing)."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)

    name: str = Field(nullable=False, min_length=1, max_length=255)
    balance: float = Field(default=settings.default_budget, ge=0.0)

    email: Optional[str] = Field(default=None)
    hashed_password: str = Field(nullable=False, min_length=1)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: Optional[datetime] = Field(default=None)
    allow_web_research: bool = Field(
        default=True, description="If true, agents may access the public web."
    )
    enable_code_review: bool = Field(default=True)
    enable_refactor: bool = Field(default=True)
    # UI theme preference (light or dark mode)
    theme: UserTheme = Field(
        default=UserTheme.light,
        sa_column=sa.Column(
            sa.Enum(UserTheme, name="usertheme"),
            nullable=False,
            server_default="light",
        ),
    )

    # Relationship collections using SQLAlchemy 2.x style (Mapped).
    tasks: ClassVar[Mapped[list["Task"]]] = relationship("Task", back_populates="tenant")
    purposes: ClassVar[Mapped[list["Purpose"]]] = relationship(
        "Purpose", back_populates="tenant"
    )
    assignments: ClassVar[Mapped[list["TenantPromptAssignment"]]] = relationship(
        "TenantPromptAssignment", back_populates="tenant", cascade="all, delete-orphan"
    )
