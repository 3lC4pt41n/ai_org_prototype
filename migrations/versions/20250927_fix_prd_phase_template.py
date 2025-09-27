"""Fix PRD pipeline_phase to point to requirements.j2"""

from alembic import op
import sqlalchemy as sa

revision = "20250927_fix_prd_phase_template"
down_revision = "20250927_cleanup_prompt_templates"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
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


def downgrade():
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE pipeline_phase
            SET prompt_template = NULL,
                agent_role = NULL
            WHERE slug = 'prd'
            """
        )
    )
