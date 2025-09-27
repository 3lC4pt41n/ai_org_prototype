"""Ensure PRD uses requirements.j2 and clean dummy entries."""

from alembic import op
import sqlalchemy as sa


# Revision identifiers, used by Alembic.
revision = "20250927_fix_prd_prompt"
down_revision = "20251205_fill_agent_roles"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # 1. PRD-Phase korrekt auf requirements.j2 mappen und Agentenrolle setzen
    conn.execute(
        sa.text(
            """
            UPDATE pipeline_phase
            SET prompt_template = 'requirements.j2',
                agent_role = 'po'
            WHERE slug = 'prd'
            """
        )
    )

    # 2. Alte Dummy-PromptTemplate-Overrides entfernen
    conn.execute(
        sa.text(
            """
            DELETE FROM prompt_template
            WHERE default_path = 'requirements.j2'
              AND (content IS NULL OR content ILIKE '%TBD%')
            """
        )
    )


def downgrade():
    conn = op.get_bind()
    # Agent-Rolle zurücksetzen (optional)
    conn.execute(
        sa.text(
            """
            UPDATE pipeline_phase
            SET agent_role = NULL
            WHERE slug = 'prd'
            """
        )
    )
