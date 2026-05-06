"""Phase 1: add persisted intent review drafts.

Revision ID: phase1_intent_review
Revises: s6_audit_log
Create Date: 2026-05-06
"""

from alembic import op
import sqlalchemy as sa

revision = "phase1_intent_review"
down_revision = "s6_audit_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "intent_review",
        sa.Column("id", sa.String(8), primary_key=True),
        sa.Column("tenant_id", sa.String, sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purpose_id", sa.String, sa.ForeignKey("purpose.id", ondelete="SET NULL"), nullable=True),
        sa.Column("raw_request", sa.Text, nullable=False),
        sa.Column("intent_json", sa.JSON, nullable=False),
        sa.Column("validation_json", sa.JSON, nullable=False),
        sa.Column("legacy_role", sa.String(100), nullable=False),
        sa.Column("requires_clarification", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("clarification_reason", sa.Text, nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_intent_review_tenant_id", "intent_review", ["tenant_id"])
    op.create_index("ix_intent_review_purpose_id", "intent_review", ["purpose_id"])
    op.create_index("ix_intent_review_status", "intent_review", ["status"])


def downgrade() -> None:
    op.drop_index("ix_intent_review_status", table_name="intent_review")
    op.drop_index("ix_intent_review_purpose_id", table_name="intent_review")
    op.drop_index("ix_intent_review_tenant_id", table_name="intent_review")
    op.drop_table("intent_review")
