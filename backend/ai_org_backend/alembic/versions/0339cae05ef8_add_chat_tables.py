"""Add chat message and context tables.

Revision ID: 20250910_add_chat_tables
Revises: 20251004_artifact_release_flag
Create Date: 2025-09-10 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# Revision identifiers, used by Alembic.
revision: str = "20250910_add_chat_tables"
down_revision: Union[str, Sequence[str], None] = "20251004_artifact_release_flag"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1. Create chatmessage table if it doesn't exist
    if not insp.has_table("chatmessage"):
        op.create_table(
            "chatmessage",
            sa.Column("id", sa.String(length=8), primary_key=True, nullable=False),
            sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False),
            sa.Column("purpose_id", sa.String(), sa.ForeignKey("purpose.id"), nullable=True),
            sa.Column("artifact_id", sa.String(), sa.ForeignKey("artifact.id"), nullable=True),
            sa.Column("task_id", sa.String(), sa.ForeignKey("task.id"), nullable=True),
            sa.Column(
                "role", sa.Enum("user", "assistant", "agent", name="chatrole"), nullable=False
            ),
            sa.Column("content", sa.String(length=5000), nullable=False),
            sa.Column("metadata", sa.JSON(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
        # Remove temporary default values (only used during table creation)
        op.alter_column("chatmessage", "created_at", server_default=None)

    # 2. Create chatthreadcontext table if it doesn't exist
    if not insp.has_table("chatthreadcontext"):
        op.create_table(
            "chatthreadcontext",
            sa.Column(
                "purpose_id",
                sa.String(),
                sa.ForeignKey("purpose.id"),
                primary_key=True,
                nullable=False,
            ),
            sa.Column("summary", sa.String(length=5000), nullable=False),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
        op.alter_column("chatthreadcontext", "updated_at", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    # Drop chatthreadcontext table if exists
    if insp.has_table("chatthreadcontext"):
        op.drop_table("chatthreadcontext")
    # Drop chatmessage table and enum type if exists
    if insp.has_table("chatmessage"):
        op.drop_table("chatmessage")
        op.execute(sa.text("DROP TYPE IF EXISTS chatrole"))
