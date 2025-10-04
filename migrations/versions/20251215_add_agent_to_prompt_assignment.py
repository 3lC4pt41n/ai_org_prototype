"""add agent column to tenant prompt assignment"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251215_add_agent_to_prompt_assignment"
down_revision = "20251202_merge_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenant_prompt_assignment",
        sa.Column("agent", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenant_prompt_assignment", "agent")
