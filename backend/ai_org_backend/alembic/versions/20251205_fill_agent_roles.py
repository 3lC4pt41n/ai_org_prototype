"""Fill agent roles for core pipeline phases."""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251205_fill_agent_roles"
down_revision = "20251204_task_dependency_updates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()

    role_map = {
        "vision": "vision",
        "prd": "po",
        "architecture": "architect",
        "architecture_review": "reviewer",
        "implementation": "planner",
    }

    update_stmt = sa.text(
        """
        UPDATE pipeline_phase
        SET agent_role = :role
        WHERE slug = :slug
          AND (agent_role IS NULL OR agent_role = '')
        """
    )

    for slug, role in role_map.items():
        connection.execute(update_stmt, {"slug": slug, "role": role})


def downgrade() -> None:
    connection = op.get_bind()

    connection.execute(
        sa.text(
            """
            UPDATE pipeline_phase
            SET agent_role = NULL
            WHERE slug IN ('vision', 'prd', 'architecture', 'architecture_review', 'implementation')
            """
        )
    )
