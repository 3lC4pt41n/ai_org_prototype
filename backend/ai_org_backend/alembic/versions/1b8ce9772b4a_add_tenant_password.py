"""add hashed_password to tenant

Revision ID: 1b8ce9772b4a
Revises: 25e81e57313f
Create Date: 2023-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '1b8ce9772b4a'
down_revision: Union[str, Sequence[str], None] = '25e81e57313f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column('tenant', sa.Column('hashed_password', sa.String(), nullable=False, server_default=''))
    op.alter_column('tenant', 'hashed_password', server_default=None)

def downgrade() -> None:
    op.drop_column('tenant', 'hashed_password')
