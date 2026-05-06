"""Phase 4: add artifact freshness status.

Revision ID: phase4_artifact_status
Revises: phase2_pipeline_graph
Create Date: 2026-05-06
"""

from alembic import op
import sqlalchemy as sa

revision = "phase4_artifact_status"
down_revision = "phase2_pipeline_graph"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("artifact", sa.Column("status", sa.String(30), nullable=False, server_default="fresh"))
    op.create_index("ix_artifact_status", "artifact", ["status"])


def downgrade() -> None:
    op.drop_index("ix_artifact_status", table_name="artifact")
    op.drop_column("artifact", "status")
