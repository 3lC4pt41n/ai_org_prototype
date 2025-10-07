"""Remove ArtifactFeedback table"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20251007_remove_artifactfeedback"
down_revision: Union[str, Sequence[str], None] = "20251006_migrate_artifactfeedback_to_chat"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema by dropping obsolete ArtifactFeedback table."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "artifactfeedback" in inspector.get_table_names():
        op.drop_table("artifactfeedback")


def downgrade() -> None:
    """Recreate ArtifactFeedback table for downgrade compatibility."""
    op.create_table(
        "artifactfeedback",
        sa.Column("id", sa.String(length=8), primary_key=True, nullable=False),
        sa.Column("artifact_id", sa.String(), sa.ForeignKey("artifact.id"), nullable=False),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("author", sa.String(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
