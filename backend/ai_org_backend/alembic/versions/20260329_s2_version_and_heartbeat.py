"""S2-03/S2-06: Add version counter and last_heartbeat_at to Task table.

Revision ID: s2_03_version_heartbeat
Revises: s1_cascade_constraints
Create Date: 2026-03-29
"""

from alembic import op
import sqlalchemy as sa

revision = "s2_03_version_heartbeat"
down_revision = "s1_cascade_constraints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name

    if dialect == "sqlite":
        # SQLite: use batch mode for ALTER TABLE
        with op.batch_alter_table("task") as batch_op:
            batch_op.add_column(
                sa.Column("version", sa.Integer(), nullable=False, server_default="0")
            )
            batch_op.add_column(
                sa.Column("last_heartbeat_at", sa.DateTime(), nullable=True)
            )
    else:
        # PostgreSQL / other
        op.add_column(
            "task",
            sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        )
        op.add_column(
            "task",
            sa.Column("last_heartbeat_at", sa.DateTime(), nullable=True),
        )


def downgrade() -> None:
    dialect = op.get_bind().dialect.name

    if dialect == "sqlite":
        with op.batch_alter_table("task") as batch_op:
            batch_op.drop_column("last_heartbeat_at")
            batch_op.drop_column("version")
    else:
        op.drop_column("task", "last_heartbeat_at")
        op.drop_column("task", "version")
