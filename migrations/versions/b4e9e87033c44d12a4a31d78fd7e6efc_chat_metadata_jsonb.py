"""convert chat metadata column to jsonb

Revision ID: b4e9e87033c44d12a4a31d78fd7e6efc
Revises: ae3f8967cb1341b39a5f44b8f0a0c1d2
Create Date: 2025-10-10 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "b4e9e87033c44d12a4a31d78fd7e6efc"
down_revision = "ae3f8967cb1341b39a5f44b8f0a0c1d2"
branch_labels = None
depends_on = None


def _has_table(conn, name: str) -> bool:
    insp = sa.inspect(conn)
    try:
        return insp.has_table(name)
    except Exception:  # pragma: no cover - inspector fallback
        return False


def _has_column(conn, table: str, column: str) -> bool:
    insp = sa.inspect(conn)
    try:
        return column in [c["name"] for c in insp.get_columns(table)]
    except Exception:  # pragma: no cover - inspector fallback
        return False


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    if not _has_table(bind, "chatmessage") or not _has_column(bind, "chatmessage", "metadata"):
        return
    op.alter_column(
        "chatmessage",
        "metadata",
        type_=postgresql.JSONB(),
        postgresql_using="metadata::jsonb",
    )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    if not _has_table(bind, "chatmessage") or not _has_column(bind, "chatmessage", "metadata"):
        return
    op.alter_column(
        "chatmessage",
        "metadata",
        type_=sa.JSON(),
        postgresql_using="metadata::json",
    )
