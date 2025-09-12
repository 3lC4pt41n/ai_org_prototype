"""Add theme field to Tenant model for Dark Mode preference.

Revision ID: 20250912_user_theme
Revises: 20250911_chat_scope_tags
Create Date: 2025-09-12 19:22:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# Revision identifiers, used by Alembic.
revision: str = "20250912_user_theme"
down_revision: Union[str, Sequence[str], None] = "20250911_chat_scope_tags"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add theme column to tenant for light/dark preference."""
    op.add_column(
        "tenant",
        sa.Column(
            "theme",
            sa.Enum("light", "dark", name="usertheme"),
            nullable=False,
            server_default="light",
        ),
    )
    # Remove default after existing rows are initialized
    op.alter_column("tenant", "theme", server_default=None)


def downgrade() -> None:
    """Remove theme column and enum."""
    op.drop_column("tenant", "theme")
    op.execute("DROP TYPE IF EXISTS usertheme")
