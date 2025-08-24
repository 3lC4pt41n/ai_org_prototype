"""add allow_web_research to tenant (boolean default true)

Revision ID: e7f1c2a9b3d44c5ea4f3d9b1c0a2f9de
Revises: 001_add_tenant
Create Date: 2025-08-24 12:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

# ⚠️ WICHTIG:
# - Alembic's default version table uses VARCHAR(32). Make sure revision ids are <= 32 chars.
# - Therefore we use a 32-char hex-like id above.

# revision identifiers, used by Alembic.
revision = "e7f1c2a9b3d44c5ea4f3d9b1c0a2f9de"
down_revision = "001_add_tenant"
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
    if not _has_table(bind, "tenant"):
        op.create_table(
            "tenant",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("balance", sa.Float(), nullable=False, server_default="0"),
            sa.Column("plan", sa.String(), nullable=False, server_default="free"),
            sa.Column(
                "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
            ),
        )

    if not _has_column(bind, "tenant", "allow_web_research"):
        op.add_column(
            "tenant",
            sa.Column("allow_web_research", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
        # After backfilling existing rows, drop server default to keep app-level defaults in control
        op.alter_column("tenant", "allow_web_research", server_default=None)


def downgrade():
    bind = op.get_bind()
    if _has_column(bind, "tenant", "allow_web_research"):
        op.drop_column("tenant", "allow_web_research")
