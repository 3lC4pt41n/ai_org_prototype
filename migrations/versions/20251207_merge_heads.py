"""merge all outstanding heads into a single head"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20251207_merge_heads"
down_revision = (
    "e29d6e0c1b5a4ad982e3725cbccb1e55",
    "b4e9e87033c44d12a4a31d78fd7e6efc",
    "20251215_add_agent_to_prompt_assignment",
    "20250927_seed_default_prompts",
    "20250927_fix_prd_phase_template",
    "f2a1c3d9e123",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
