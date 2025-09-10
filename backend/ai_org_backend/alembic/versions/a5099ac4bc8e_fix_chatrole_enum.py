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
    """Upgrade schema: replace chatrole ENUM with lowercase values."""
    # Rename old enum
    op.execute("ALTER TYPE chatrole RENAME TO chatrole_old;")

    # Create new enum with lowercase values
    op.execute("CREATE TYPE chatrole AS ENUM ('user', 'assistant', 'agent');")

    # Alter column to use new enum (convert values to lowercase first)
    op.execute(
        "ALTER TABLE chatmessage "
        "ALTER COLUMN role TYPE chatrole "
        "USING lower(role)::chatrole;"
    )

    # Drop old enum
    op.execute("DROP TYPE chatrole_old;")

    # Normalize created_at columns (optional cleanup)
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
    op.alter_column(
        "artifactfeedback",
        "created_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        type_=sa.DateTime(),
        existing_nullable=False,
        existing_server_default=sa.text("now()"),
    )


def downgrade() -> None:
    """Downgrade schema: restore uppercase chatrole enum."""
    # Recreate old enum
    op.execute("CREATE TYPE chatrole_old AS ENUM ('USER', 'ASSISTANT', 'AGENT');")

    # Revert column back to old enum
    op.execute(
        "ALTER TABLE chatmessage "
        "ALTER COLUMN role TYPE chatrole_old "
        "USING upper(role)::chatrole_old;"
    )

    # Drop new enum
    op.execute("DROP TYPE chatrole;")

    # Rename back
    op.execute("ALTER TYPE chatrole_old RENAME TO chatrole;")

    # Revert timestamp columns
    op.alter_column(
        "artifactfeedback",
        "created_at",
        existing_type=sa.DateTime(),
        type_=postgresql.TIMESTAMP(timezone=True),
        existing_nullable=False,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "chatmessage",
        "created_at",
        existing_type=sa.DateTime(),
        type_=postgresql.TIMESTAMP(timezone=True),
        existing_nullable=False,
    )
    op.alter_column(
        "chatthreadcontext",
        "updated_at",
        existing_type=sa.DateTime(),
        type_=postgresql.TIMESTAMP(timezone=True),
        existing_nullable=False,
    )
