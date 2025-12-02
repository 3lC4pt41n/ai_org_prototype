"""add allow_web_research to tenant

Revision ID: 20250808_add_tenant_allow_web_research
Revises: 20250730_create_task_table
Create Date: 2025-08-08 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20250808_add_tenant_allow_web_research"
down_revision: Union[str, Sequence[str], None] = "20250730_create_task_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_columns = [c["name"] for c in insp.get_columns("tenant")]
    if "allow_web_research" not in existing_columns:
        op.add_column(
            "tenant",
            sa.Column(
                "allow_web_research",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
        )
        op.alter_column("tenant", "allow_web_research", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_columns = [c["name"] for c in insp.get_columns("tenant")]
    if "allow_web_research" in existing_columns:
        op.drop_column("tenant", "allow_web_research")
