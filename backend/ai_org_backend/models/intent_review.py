"""Persisted intent review drafts for UI correction before execution."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Column, JSON, Text
from sqlmodel import Field, SQLModel


class IntentReview(SQLModel, table=True):
    """User-visible compiled intent that can be edited before graph start."""

    __tablename__ = "intent_review"

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8], primary_key=True, max_length=8)
    tenant_id: str = Field(foreign_key="tenant.id", nullable=False, index=True)
    purpose_id: Optional[str] = Field(default=None, foreign_key="purpose.id", index=True)
    raw_request: str = Field(sa_column=Column(Text, nullable=False))
    intent_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    validation_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    legacy_role: str = Field(max_length=100)
    requires_clarification: bool = Field(default=False, nullable=False)
    clarification_reason: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    status: str = Field(default="draft", max_length=30)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: Optional[datetime] = Field(default=None)
