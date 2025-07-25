from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlmodel import SQLModel, Field, Relationship

from ..settings import settings

if TYPE_CHECKING:
    from .task import Task
    from .purpose import Purpose


class Tenant(SQLModel, table=True):
    """Simple tenant model (multi-tenant future-proofing)."""

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), 
        primary_key=True
    )
    
    name: str = Field(nullable=False, min_length=1, max_length=255, unique=True)
    balance: float = Field(default=settings.default_budget, ge=0.0)  # Balance >= 0
    
    # Additional useful fields
    email: Optional[str] = Field(default=None, max_length=255)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: Optional[datetime] = Field(default=None)
    
    # Spending limits and tracking
    monthly_budget_limit: Optional[float] = Field(default=None, ge=0.0)
    current_monthly_spent: float = Field(default=0.0, ge=0.0)

    # SQLModel-Style Relationships
    tasks: List["Task"] = Relationship(
        back_populates="tenant",
        sa_relationship_kwargs={"foreign_keys": "[Task.tenant_id]"}
    )
    
    purposes: List["Purpose"] = Relationship(
        back_populates="tenant", 
        sa_relationship_kwargs={"foreign_keys": "[Purpose.tenant_id]"}
    )

    def __str__(self) -> str:
        return f"Tenant({self.id}: {self.name})"

    def __repr__(self) -> str:
        return f"Tenant(id='{self.id}', name='{self.name}', balance={self.balance})"

    @property
    def active_tasks_count(self) -> int:
        """Get count of active tasks for this tenant."""
        if not self.tasks:
            return 0
        return len([task for task in self.tasks if getattr(task, 'is_active', True)])

    @property
    def active_purposes_count(self) -> int:
        """Get count of active purposes for this tenant."""
        if not self.purposes:
            return 0
        return len([purpose for purpose in self.purposes if getattr(purpose, 'is_active', True)])

    @property
    def remaining_monthly_budget(self) -> Optional[float]:
        """Calculate remaining monthly budget."""
        if self.monthly_budget_limit is None:
            return None
        return max(0.0, self.monthly_budget_limit - self.current_monthly_spent)

    @property
    def is_over_budget(self) -> bool:
        """Check if tenant has exceeded monthly budget."""
        if self.monthly_budget_limit is None:
            return False
        return self.current_monthly_spent > self.monthly_budget_limit

    def spend(self, amount: float) -> bool:
        """
        Deduct amount from balance and track monthly spending.
        Returns True if successful, False if insufficient funds.
        """
        if amount <= 0:
            raise ValueError("Spend amount must be positive")
        
        if self.balance < amount:
            return False
        
        self.balance -= amount
        self.current_monthly_spent += amount
        self.updated_at = datetime.utcnow()
        return True

    def add_funds(self, amount: float) -> None:
        """Add funds to tenant balance."""
        if amount <= 0:
            raise ValueError("Amount must be positive")
        
        self.balance += amount
        self.updated_at = datetime.utcnow()

    def reset_monthly_spending(self) -> None:
        """Reset monthly spending counter (typically called monthly)."""
        self.current_monthly_spent = 0.0
        self.updated_at = datetime.utcnow()

    def deactivate(self) -> None:
        """Deactivate this tenant."""
        self.is_active = False
        self.updated_at = datetime.utcnow()

    def activate(self) -> None:
        """Activate this tenant."""
        self.is_active = True
        self.updated_at = datetime.utcnow()

    def set_monthly_budget(self, budget_limit: Optional[float]) -> None:
        """Set monthly budget limit."""
        if budget_limit is not None and budget_limit < 0:
            raise ValueError("Budget limit must be non-negative")
        
        self.monthly_budget_limit = budget_limit
        self.updated_at = datetime.utcnow()

    @classmethod
    def create_with_validation(
        cls,
        name: str,
        email: Optional[str] = None,
        initial_balance: Optional[float] = None,
        monthly_budget_limit: Optional[float] = None
    ) -> "Tenant":
        """Create a new tenant with validation."""
        if not name or not name.strip():
            raise ValueError("Tenant name cannot be empty")
        
        if len(name.strip()) > 255:
            raise ValueError("Tenant name too long (max 255 characters)")
        
        if email and len(email) > 255:
            raise ValueError("Email too long (max 255 characters)")
        
        balance = initial_balance if initial_balance is not None else settings.default_budget
        if balance < 0:
            raise ValueError("Initial balance cannot be negative")
            
        return cls(
            name=name.strip(),
            email=email.strip() if email else None,
            balance=balance,
            monthly_budget_limit=monthly_budget_limit
        )
