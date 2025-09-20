"""Rename taskdependency table to task_dependency."""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20251204_fix_taskdependency_name"
down_revision = "20251203_prompt_template_m2m"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.rename_table("taskdependency", "task_dependency")


def downgrade() -> None:
    op.rename_table("task_dependency", "taskdependency")
