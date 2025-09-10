"""Fix chatrole enum to lowercase

Revision ID: a5099ac4bc8e
Revises: 20250910_add_chat_tables
Create Date: 2025-09-10 12:30:05.767161
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a5099ac4bc8e"
down_revision: Union[str, Sequence[str], None] = "20250910_add_chat_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: normalize chatrole enum and fix timestamp columns."""

    # --- Fix chatrole enum ---
    op.execute("ALTER TYPE chatrole RENAME TO chatrole_old;")
    op.execute("CREATE TYPE chatrole AS ENUM ('user', 'assistant', 'agent');")
    op.execute(
        "ALTER TABLE chatmessage "
        "ALTER COLUMN role TYPE chatrole "
        "USING lower(role::text)::chatrole;"
    )
    op.execute("DROP TYPE chatrole_old;")

    # --- Normalize timestamp columns (remove timezone, keep as naive DateTime) ---
    op.alter_column(
        "artifactfeedback",
        "content",
        existing_type=sa.TEXT(),
        type_=sa.String(),
        existing_nullable=False,
    )
    op.alter_column(
        "artifactfeedback",
        "created_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        type_=sa.DateTime(),
        existing_nullable=False,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "chatmessage",
        "created_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        type_=sa.DateTime(),
        existing_nullable=False,
    )
    op.alter_column(
        "chatthreadcontext",
        "updated_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        type_=sa.DateTime(),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Downgrade schema: restore uppercase chatrole enum and timestamp columns."""

    # --- Revert chatrole enum ---
    op.execute("CREATE TYPE chatrole_old AS ENUM ('USER', 'ASSISTANT', 'AGENT');")
    op.execute(
        "ALTER TABLE chatmessage "
        "ALTER COLUMN role TYPE chatrole_old "
        "USING upper(role::text)::chatrole_old;"
    )
    op.execute("DROP TYPE chatrole;")
    op.execute("ALTER TYPE chatrole_old RENAME TO chatrole;")

    # --- Revert timestamp columns ---
    op.alter_column(
        "chatthreadcontext",
        "updated_at",
        existing_type=sa.DateTime(),
        type_=postgresql.TIMESTAMP(timezone=True),
        existing_nullable=False,
    )
    op.alter_column(
        "chatmessage",
        "created_at",
        existing_type=sa.DateTime(),
        type_=postgresql.TIMESTAMP(timezone=True),
        existing_nullable=False,
    )
    op.alter_column(
        "artifactfeedback",
        "created_at",
        existing_type=sa.DateTime(),
        type_=postgresql.TIMESTAMP(timezone=True),
        existing_nullable=False,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "artifactfeedback",
        "content",
        existing_type=sa.String(),
        type_=sa.TEXT(),
        existing_nullable=False,
    )
