"""add artifact_feedback table with author

Revision ID: 0a1e1fb0dca64e9c96b8fc5f1a8e3b12
Revises: e7f1c2a9b3d44c5ea4f3d9b1c0a2f9de
Create Date: 2025-09-30 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0a1e1fb0dca64e9c96b8fc5f1a8e3b12"
down_revision = "e7f1c2a9b3d44c5ea4f3d9b1c0a2f9de"
branch_labels = None
depends_on = None

def _has_table(conn, name: str) -> bool:
    insp = sa.inspect(conn)
    try:
        return insp.has_table(name)
    except Exception:
        return False

def _has_column(conn, table: str, column: str) -> bool:
    insp = sa.inspect(conn)
    try:
        cols = [c["name"] for c in insp.get_columns(table)]
        return column in cols
    except Exception:
        return False

def upgrade():
    bind = op.get_bind()
    if not _has_table(bind, "artifact_feedback"):
        op.create_table(
            "artifact_feedback",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("artifact_id", sa.String(), sa.ForeignKey("artifact.id"), nullable=False),
            sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False),
            sa.Column("author", sa.String(), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("approved", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.alter_column("artifact_feedback", "version", server_default=None)
        op.alter_column("artifact_feedback", "approved", server_default=None)
        op.alter_column("artifact_feedback", "created_at", server_default=None)
    elif not _has_column(bind, "artifact_feedback", "author"):
        op.add_column("artifact_feedback", sa.Column("author", sa.String(), nullable=True))

def downgrade():
    bind = op.get_bind()
    if _has_table(bind, "artifact_feedback"):
        op.drop_table("artifact_feedback")
