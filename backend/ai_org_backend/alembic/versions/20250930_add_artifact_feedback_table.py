"""add artifact_feedback table"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20250930_add_artifact_feedback_table"
down_revision: Union[str, Sequence[str], None] = "20250810_add_qa_review_refactor_agents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # If an old table with underscore exists -> rename to the new name
    if insp.has_table("artifact_feedback") and not insp.has_table("artifactfeedback"):
        op.rename_table("artifact_feedback", "artifactfeedback")

    # Create table if it does not exist
    if not insp.has_table("artifactfeedback"):
        op.create_table(
            "artifactfeedback",
            sa.Column("id", sa.String(length=8), primary_key=True, nullable=False),
            sa.Column("artifact_id", sa.String(), sa.ForeignKey("artifact.id"), nullable=False),
            sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False),
            sa.Column("author", sa.String(), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("approved", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
        # Remove default server values (only used for CREATE)
        op.alter_column("artifactfeedback", "version", server_default=None)
        op.alter_column("artifactfeedback", "approved", server_default=None)
        op.alter_column("artifactfeedback", "created_at", server_default=None)

    # Do NOT create misleading autogenerate table "feedback". Drop it later if it exists.


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if insp.has_table("artifactfeedback"):
        op.drop_table("artifactfeedback")
