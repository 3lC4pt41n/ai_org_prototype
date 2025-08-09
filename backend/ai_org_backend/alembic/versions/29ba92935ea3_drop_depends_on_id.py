"""drop depends_on_id

Revision ID: 29ba92935ea3
Revises:
Create Date: 2025-07-23 12:41:42.500169

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "29ba92935ea3"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _ensure_task_dependency_table() -> None:
    """Create task_dependency if it does not exist yet (idempotent)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("task_dependency"):
        op.create_table(
            "task_dependency",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("from_id", sa.String(length=36), nullable=False),
            sa.Column("to_id", sa.String(length=36), nullable=False),
        )
        op.create_index("ix_task_dep_from_id", "task_dependency", ["from_id"])
        op.create_index("ix_task_dep_to_id", "task_dependency", ["to_id"])


def upgrade() -> None:
    """Upgrade schema."""
    _ensure_task_dependency_table()

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    task_cols = [c["name"] for c in inspector.get_columns("task")]
    if "depends_on_id" in task_cols:
        op.execute(
            sa.text(
                """
                INSERT INTO task_dependency(from_id, to_id)
                SELECT id, depends_on_id FROM task WHERE depends_on_id IS NOT NULL
                """
            )
        )
        with op.batch_alter_table("task") as batch:
            batch.drop_column("depends_on_id")


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    task_cols = [c["name"] for c in inspector.get_columns("task")]
    if "depends_on_id" not in task_cols:
        with op.batch_alter_table("task") as batch:
            batch.add_column(sa.Column("depends_on_id", sa.String(length=36), nullable=True))

    if inspector.has_table("task_dependency"):
        op.execute(
            sa.text(
                """
                UPDATE task
                SET depends_on_id = (
                    SELECT td.to_id FROM task_dependency td
                    WHERE td.from_id = task.id
                    LIMIT 1
                )
                WHERE depends_on_id IS NULL
                """
            )
        )
