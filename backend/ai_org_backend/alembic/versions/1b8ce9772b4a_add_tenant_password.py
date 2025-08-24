"""add hashed_password to tenant

Revision ID: 1b8ce9772b4a
Revises: 25e81e57313f
Create Date: 2023-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = '1b8ce9772b4a'
down_revision: Union[str, Sequence[str], None] = '25e81e57313f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()

    if 'tenant' not in tables:
        op.create_table(
            'tenant',
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('name', sa.String(), nullable=False),
            sa.Column('balance', sa.Float(), nullable=False, server_default='0'),
            sa.Column('plan', sa.String(), nullable=False, server_default='free'),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('hashed_password', sa.String(), nullable=False, server_default=''),
            sa.PrimaryKeyConstraint('id'),
        )
    elif 'hashed_password' not in [c['name'] for c in inspector.get_columns('tenant')]:
        op.add_column('tenant', sa.Column('hashed_password', sa.String(), nullable=False, server_default=''))
        op.alter_column('tenant', 'hashed_password', server_default=None)

def downgrade() -> None:
    op.drop_column('tenant', 'hashed_password')
