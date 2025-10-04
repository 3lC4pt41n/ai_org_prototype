"""Add agent column to tenant_prompt_assignment and adjust unique index."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# Revision identifiers, used by Alembic.
revision = "20250928_add_agent_to_prompt_assignment"
down_revision = "20250927_cleanup_prompt_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenant_prompt_assignment",
        sa.Column("agent", sa.String(length=100), nullable=True),
    )

    op.drop_index(
        "ix_tenant_prompt_assignment_tenant_phase",
        table_name="tenant_prompt_assignment",
    )

    op.execute(
        text(
            """
            UPDATE tenant_prompt_assignment AS t
            SET agent = p.agent
            FROM prompt_template AS p
            WHERE p.id = t.prompt_template_id
            """
        )
    )

    op.execute(
        text(
            """
            CREATE UNIQUE INDEX ix_tenant_prompt_assignment_tenant_phase_agent
            ON tenant_prompt_assignment (tenant_id, phase_slug, COALESCE(agent, ''))
            """
        )
    )


def downgrade() -> None:
    op.execute(
        text(
            "DROP INDEX IF EXISTS ix_tenant_prompt_assignment_tenant_phase_agent"
        )
    )

    op.create_index(
        "ix_tenant_prompt_assignment_tenant_phase",
        "tenant_prompt_assignment",
        ["tenant_id", "phase_slug"],
        unique=True,
    )

    op.drop_column("tenant_prompt_assignment", "agent")
