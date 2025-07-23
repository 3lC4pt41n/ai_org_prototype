"""drop depends_on_id

Revision ID: 25e81e57313f
Revises: 29ba92935ea3
Create Date: 2025-07-23 17:55:42.797371

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '25e81e57313f'
down_revision: Union[str, Sequence[str], None] = '29ba92935ea3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
