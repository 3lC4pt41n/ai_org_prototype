"""S6: Add audit_log table for security event tracking.

Revision ID: s6_audit_log
Revises: s5_review_merge
Create Date: 2026-03-30
"""

from alembic import op
import sqlalchemy as sa

revision = "s6_audit_log"
down_revision = "s5_review_merge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(8), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String,
            sa.ForeignKey("tenant.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("detail", sa.String(2000), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime,
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_audit_tenant", "audit_log", ["tenant_id"])
    op.create_index("ix_audit_action", "audit_log", ["action"])
    op.create_index("ix_audit_created", "audit_log", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_created", table_name="audit_log")
    op.drop_index("ix_audit_action", table_name="audit_log")
    op.drop_index("ix_audit_tenant", table_name="audit_log")
    op.drop_table("audit_log")
