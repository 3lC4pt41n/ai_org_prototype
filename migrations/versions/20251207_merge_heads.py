"""maintain linear history after consolidating heads"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20251207_merge_heads"
down_revision = "20251215_add_agent_to_prompt_assignment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
