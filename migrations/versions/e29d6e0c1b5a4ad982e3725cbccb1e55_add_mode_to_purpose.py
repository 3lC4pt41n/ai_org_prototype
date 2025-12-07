"""add mode column to purpose

Revision ID: e29d6e0c1b5a4ad982e3725cbccb1e55
Revises: ae3f8967cb1341b39a5f44b8f0a0c1d2
Create Date: 2025-10-06 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "e29d6e0c1b5a4ad982e3725cbccb1e55"
down_revision = "b4e9e87033c44d12a4a31d78fd7e6efc"
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
    if _has_table(bind, "purpose") and not _has_column(bind, "purpose", "mode"):
        op.add_column(
            "purpose",
            sa.Column("mode", sa.String(), nullable=False, server_default="manual"),
        )
        op.alter_column("purpose", "mode", server_default=None)


def downgrade():
    bind = op.get_bind()
    if _has_table(bind, "purpose") and _has_column(bind, "purpose", "mode"):
        op.drop_column("purpose", "mode")
