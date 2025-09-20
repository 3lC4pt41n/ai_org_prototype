"""Add dependency_type to task_dependency table."""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251204_task_dependency_updates"
down_revision = "20251204_fix_taskdependency_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "task_dependency",
        sa.Column("dependency_type", sa.String(length=50), nullable=False, server_default="blocks"),
    )
    op.alter_column("task_dependency", "dependency_type", server_default=None)
    # Optionally, consider adding foreign key constraints on task_dependency if needed.


def downgrade() -> None:
    op.drop_column("task_dependency", "dependency_type")
