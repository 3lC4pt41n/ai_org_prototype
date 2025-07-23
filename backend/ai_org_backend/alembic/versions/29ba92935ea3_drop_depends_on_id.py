"""drop depends_on_id

Revision ID: 29ba92935ea3
Revises: 
Create Date: 2025-07-23 12:41:42.500169

"""
from typing import Sequence, Union

from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401


# revision identifiers, used by Alembic.
revision: str = '29ba92935ea3'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        INSERT INTO task_dependency(from_id, to_id)
        SELECT id, depends_on_id FROM task WHERE depends_on_id IS NOT NULL
        """
    )
    op.drop_column("task", "depends_on_id")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column("task", sa.Column("depends_on_id", sa.String(), nullable=True))
