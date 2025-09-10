"""normalize legacy ChatRole values to lowercase

Revision ID: ae3f8967cb1341b39a5f44b8f0a0c1d2
Revises: 0a1e1fb0dca64e9c96b8fc5f1a8e3b12
Create Date: 2025-10-05 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "ae3f8967cb1341b39a5f44b8f0a0c1d2"
down_revision = "0a1e1fb0dca64e9c96b8fc5f1a8e3b12"
branch_labels = None
depends_on = None

def _has_table(conn, name: str) -> bool:
    insp = sa.inspect(conn)
    try:
        return insp.has_table(name)
    except Exception:
        return False

def upgrade():
    bind = op.get_bind()
    if _has_table(bind, "chatmessage"):
        op.execute(
            """
            UPDATE chatmessage
            SET role = lower(role::text)::chatrole
            WHERE role::text IN ('USER', 'ASSISTANT', 'AGENT')
            """
        )

def downgrade():
    # Irreversible data normalization
    pass
