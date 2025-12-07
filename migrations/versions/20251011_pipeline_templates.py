"""pipeline templates"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20251011_pipeline_templates"
down_revision = "20250927_fix_prd_phase_template"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Original migration managed pipeline templates; now a no-op placeholder.
    pass


def downgrade() -> None:
    # Placeholder downgrade matching the no-op upgrade.
    pass
