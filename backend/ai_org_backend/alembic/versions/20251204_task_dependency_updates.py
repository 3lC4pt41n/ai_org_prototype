"""Add dependency_type to task_dependency table."""

# revision identifiers, used by Alembic.
revision = "20251204_task_dependency_updates"
down_revision = "20251204_fix_taskdependency_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Column already present, skip
    pass


def downgrade() -> None:
    from alembic import op

    op.drop_column("task_dependency", "dependency_type")
