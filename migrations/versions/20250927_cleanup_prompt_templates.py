"""cleanup prompt templates"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20250927_cleanup_prompt_templates"
down_revision = "0a1e1fb0dca64e9c96b8fc5f1a8e3b12"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # This migration previously removed obsolete prompt templates.
    # It is now a no-op placeholder to maintain history continuity.
    pass


def downgrade() -> None:
    # Placeholder downgrade matching the no-op upgrade.
    pass
