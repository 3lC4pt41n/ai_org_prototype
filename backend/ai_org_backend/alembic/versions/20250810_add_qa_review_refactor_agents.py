"""add code review and refactor flags

Revision ID: 20250810_add_qa_review_refactor_agents
Revises: 20250808_add_tenant_allow_web_research
Create Date: 2025-08-10 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '20250810_add_qa_review_refactor_agents'
down_revision: Union[str, Sequence[str], None] = '20250808_add_tenant_allow_web_research'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'tenant',
        sa.Column('enable_code_review', sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        'tenant',
        sa.Column('enable_refactor', sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    # remove server defaults after initial rows populated
    op.alter_column('tenant', 'enable_code_review', server_default=None)
    op.alter_column('tenant', 'enable_refactor', server_default=None)

    op.add_column(
        'task',
        sa.Column('issues_found', sa.Integer(), nullable=False, server_default=sa.text('0')),
    )
    op.alter_column('task', 'issues_found', server_default=None)


def downgrade() -> None:
    op.drop_column('task', 'issues_found')
    op.drop_column('tenant', 'enable_refactor')
    op.drop_column('tenant', 'enable_code_review')
