"""S5: Add code_review_finding, merge_conflict tables + task review fields.

Revision ID: s5_review_merge
Revises: s3_artifact_versioning
Create Date: 2026-03-30
"""

from alembic import op
import sqlalchemy as sa

revision = "s5_review_merge"
down_revision = "s3_artifact_versioning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # ── code_review_finding table ──
    op.create_table(
        "code_review_finding",
        sa.Column("id", sa.String(8), primary_key=True),
        sa.Column("task_id", sa.String, sa.ForeignKey("task.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purpose_id", sa.String, sa.ForeignKey("purpose.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", sa.String, sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("category", sa.String(30), server_default="other"),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("file_path", sa.String(500), nullable=True),
        sa.Column("line_number", sa.Integer, nullable=True),
        sa.Column("suggested_fix", sa.Text, nullable=True),
        sa.Column("code_snippet", sa.Text, nullable=True),
        sa.Column("fixed", sa.Boolean, server_default="0", nullable=False),
        sa.Column("fix_task_id", sa.String, sa.ForeignKey("task.id", ondelete="SET NULL"), nullable=True),
        sa.Column("fix_commit_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_crf_task_id", "code_review_finding", ["task_id"])
    op.create_index("ix_crf_purpose_id", "code_review_finding", ["purpose_id"])
    op.create_index("ix_crf_severity", "code_review_finding", ["severity"])

    # ── merge_conflict table ──
    op.create_table(
        "merge_conflict",
        sa.Column("id", sa.String(8), primary_key=True),
        sa.Column("purpose_id", sa.String, sa.ForeignKey("purpose.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", sa.String, sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_a_id", sa.String, sa.ForeignKey("task.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_b_id", sa.String, sa.ForeignKey("task.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("conflict_type", sa.String(50), server_default="content_overlap"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), server_default="open"),
        sa.Column("resolution_task_id", sa.String, sa.ForeignKey("task.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_mc_purpose_id", "merge_conflict", ["purpose_id"])

    # ── New columns on task table ──
    if dialect == "postgresql":
        op.add_column("task", sa.Column("code_review_status", sa.String(30), nullable=True))
        op.add_column("task", sa.Column("review_rounds", sa.Integer, server_default="0", nullable=False))
    else:
        # SQLite: add columns with defaults
        op.add_column("task", sa.Column("code_review_status", sa.String(30), nullable=True))
        op.add_column("task", sa.Column("review_rounds", sa.Integer, server_default="0", nullable=True))


def downgrade() -> None:
    op.drop_index("ix_mc_purpose_id", table_name="merge_conflict")
    op.drop_table("merge_conflict")
    op.drop_index("ix_crf_severity", table_name="code_review_finding")
    op.drop_index("ix_crf_purpose_id", table_name="code_review_finding")
    op.drop_index("ix_crf_task_id", table_name="code_review_finding")
    op.drop_table("code_review_finding")

    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "postgresql":
        op.drop_column("task", "review_rounds")
        op.drop_column("task", "code_review_status")
