"""Add ArtifactFeedback table

Revision ID: d27cd98b999b
Revises: 20250930_add_artifact_feedback_table
Create Date: 2025-09-05 23:26:09.376469

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d27cd98b999b"
down_revision: Union[str, Sequence[str], None] = "20250930_add_artifact_feedback_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
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
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    # Alte Tabelle entfernen, falls vorhanden
    if op.get_bind().dialect.has_table(op.get_bind(), "artifact_feedback"):
        op.drop_table("artifact_feedback")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("artifactfeedback")
