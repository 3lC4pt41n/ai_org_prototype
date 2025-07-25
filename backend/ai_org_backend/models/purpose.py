from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, List, Optional

from sqlmodel import SQLModel, Field, Relationship

if TYPE_CHECKING:
    from .tenant import Tenant
    from .task import Task


class Purpose(SQLModel, table=True):
    """High level project purpose."""

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4())[:8], 
        primary_key=True,
        min_length=8,
        max_length=8
    )
    
    tenant_id: str = Field(foreign_key="tenant.id", nullable=False)
    name: str = Field(nullable=False, min_length=1, max_length=255)
    
    description: Optional[str] = Field(default=None, max_length=1000)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: Optional[datetime] = Field(default=None)

    # SQLModel-Style Relationships
    tenant: "Tenant" = Relationship(
        back_populates="purposes",
        sa_relationship_kwargs={"foreign_keys": "[Purpose.tenant_id]"}
    )
    
    tasks: List["Task"] = Relationship(
        back_populates="purpose",
        sa_relationship_kwargs={"foreign_keys": "[Task.purpose_id]"}
    )

    def __str__(self) -> str:
        return f"Purpose({self.id}: {self.name})"

    def __repr__(self) -> str:
        return f"Purpose(id='{self.id}', name='{self.name}', tenant_id='{self.tenant_id}')"

    @property
    def active_tasks_count(self) -> int:
        """Get count of active tasks for this purpose."""
        if not self.tasks:
            return 0
        return len([task for task in self.tasks if getattr(task, 'is_active', True)])

    def deactivate(self) -> None:
        """Deactivate this purpose and optionally its tasks."""
        self.is_active = False
        self.updated_at = datetime.utcnow()

    def activate(self) -> None:
        """Activate this purpose."""
        self.is_active = True
        self.updated_at = datetime.utcnow()

    @classmethod
    def create_with_validation(
        cls,
        tenant_id: str,
        name: str,
        description: Optional[str] = None
    ) -> "Purpose":
        """Create a new purpose with validation."""
        if not name or not name.strip():
            raise ValueError("Purpose name cannot be empty")
        
        if len(name.strip()) > 255:
            raise ValueError("Purpose name too long (max 255 characters)")
            
        return cls(
            tenant_id=tenant_id,
            name=name.strip(),
            description=description.strip() if description else None
        )
