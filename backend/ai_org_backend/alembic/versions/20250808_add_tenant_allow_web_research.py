"""add allow_web_research to tenant

Revision ID: 20250808_add_tenant_allow_web_research
Revises: 1b8ce9772b4a
Create Date: 2025-08-08 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '20250808_add_tenant_allow_web_research'
down_revision: Union[str, Sequence[str], None] = '1b8ce9772b4a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'tenant',
        sa.Column('allow_web_research', sa.Boolean(), nullable=False, server_default=sa.text('0')),
    )
    op.alter_column('tenant', 'allow_web_research', server_default=None)


def downgrade() -> None:
    op.drop_column('tenant', 'allow_web_research')
