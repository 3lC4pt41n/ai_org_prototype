"""Add tenant and purpose scope to persisted graphs.

Revision ID: graph_tenant_scope
Revises: phase4_artifact_status
Create Date: 2026-05-06
"""

from alembic import op
import sqlalchemy as sa

revision = "graph_tenant_scope"
down_revision = "phase4_artifact_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pipeline_graphs", sa.Column("tenant_id", sa.String, sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=True))
    op.add_column("pipeline_graphs", sa.Column("purpose_id", sa.String, sa.ForeignKey("purpose.id", ondelete="SET NULL"), nullable=True))
    op.create_index("ix_pipeline_graphs_tenant_id", "pipeline_graphs", ["tenant_id"])
    op.create_index("ix_pipeline_graphs_purpose_id", "pipeline_graphs", ["purpose_id"])


def downgrade() -> None:
    op.drop_index("ix_pipeline_graphs_purpose_id", table_name="pipeline_graphs")
    op.drop_index("ix_pipeline_graphs_tenant_id", table_name="pipeline_graphs")
    op.drop_column("pipeline_graphs", "purpose_id")
    op.drop_column("pipeline_graphs", "tenant_id")
