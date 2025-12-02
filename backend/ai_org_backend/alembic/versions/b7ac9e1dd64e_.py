"""empty message

Revision ID: b7ac9e1dd64e
Revises: a5099ac4bc8e
Create Date: 2025-09-10 19:28:03.047453

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7ac9e1dd64e'
down_revision: Union[str, Sequence[str], None] = 'a5099ac4bc8e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Füge Spalte 'mode' hinzu, default = 'manual'
    op.add_column(
        "purpose",
        sa.Column("mode", sa.String(), nullable=False, server_default="manual"),
    )
    # Default entfernen, damit neue Einträge explizit setzen müssen
    op.alter_column("purpose", "mode", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("purpose", "mode")
