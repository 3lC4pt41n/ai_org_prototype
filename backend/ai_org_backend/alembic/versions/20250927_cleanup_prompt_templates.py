"""Cleanup prompt_template overrides so default files are used"""

from alembic import op
import sqlalchemy as sa

# Revision identifiers, used by Alembic.
revision = "20250927_cleanup_prompt_templates"
down_revision = "20250927_fix_prd_prompt"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            DELETE FROM prompt_template
            WHERE default_path = 'requirements.j2'
               OR name = 'requirements.j2'
            """
        )
    )
    conn.execute(
        sa.text(
            """
            DELETE FROM prompt_template
            WHERE default_path IN ('vision.j2','architect.j2','review.j2','planner.j2')
            """
        )
    )


def downgrade() -> None:
    # kein restore – neu einfügen wäre Seed-Aufgabe
    pass
