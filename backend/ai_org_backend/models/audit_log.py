"""S6: Audit log model for security-relevant events.

Records authentication attempts, permission changes, and other
security-sensitive operations for compliance and forensic analysis.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


class AuditAction(str, Enum):
    """Categories of auditable actions."""

    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILURE = "login_failure"
    REGISTER = "register"
    TOKEN_REFRESH = "token_refresh"
    APPROVAL = "approval"
    REJECTION = "rejection"
    TASK_CREATE = "task_create"
    TASK_STATUS_CHANGE = "task_status_change"
    SETTINGS_CHANGE = "settings_change"
    RATE_LIMIT_HIT = "rate_limit_hit"
    DANGEROUS_INPUT = "dangerous_input"


class AuditLog(SQLModel, table=True):
    """Immutable audit trail for security-relevant events."""

    __tablename__ = "audit_log"

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8], primary_key=True, max_length=8)
    tenant_id: Optional[str] = Field(default=None, foreign_key="tenant.id")
    action: str = Field(max_length=50)
    detail: Optional[str] = Field(default=None, max_length=2000)
    ip_address: Optional[str] = Field(default=None, max_length=45)
    user_agent: Optional[str] = Field(default=None, max_length=500)
    request_id: Optional[str] = Field(default=None, max_length=64)
    created_at: datetime = Field(default_factory=datetime.utcnow)
