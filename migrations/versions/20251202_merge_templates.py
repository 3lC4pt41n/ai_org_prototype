"""merge heads pipeline_templates and prompt_templates"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20251202_merge_templates"
down_revision = ("20251011_pipeline_templates", "20251201_prompt_templates")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
