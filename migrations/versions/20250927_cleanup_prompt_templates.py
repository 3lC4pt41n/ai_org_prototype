"""cleanup prompt templates"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20250927_cleanup_prompt_templates"
down_revision = "f2a1c3d9e123"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # This migration previously removed obsolete prompt templates.
    # It is now a no-op placeholder to maintain history continuity.
    pass


def downgrade() -> None:
    # Placeholder downgrade matching the no-op upgrade.
    pass
