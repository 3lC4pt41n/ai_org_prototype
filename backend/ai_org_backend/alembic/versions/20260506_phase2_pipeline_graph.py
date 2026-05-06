"""Phase 2: add PipelineGraph v2 persistence tables.

Revision ID: phase2_pipeline_graph
Revises: phase1_intent_review
Create Date: 2026-05-06
"""

from alembic import op
import sqlalchemy as sa

revision = "phase2_pipeline_graph"
down_revision = "phase1_intent_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pipeline_graphs",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("template_family", sa.String(100), nullable=True),
        sa.Column("intent_json", sa.JSON, nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "pipeline_nodes",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("graph_id", sa.String(100), sa.ForeignKey("pipeline_graphs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(50), nullable=False),
        sa.Column("capability", sa.String(255), nullable=False),
        sa.Column("input_schema", sa.JSON, nullable=False),
        sa.Column("output_schema", sa.JSON, nullable=False),
        sa.Column("retry_policy", sa.JSON, nullable=False),
        sa.Column("timeout_s", sa.Integer, nullable=False, server_default="300"),
        sa.Column("max_revisions", sa.Integer, nullable=False, server_default="0"),
        sa.Column("requires_human_approval", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("cost_budget", sa.JSON, nullable=True),
        sa.Column("metadata", sa.JSON, nullable=False),
    )
    op.create_table(
        "pipeline_edges",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("graph_id", sa.String(100), sa.ForeignKey("pipeline_graphs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("target", sa.String(100), nullable=False),
        sa.Column("condition", sa.String(500), nullable=True),
        sa.Column("activation", sa.String(20), nullable=False, server_default="all"),
        sa.Column("edge_type", sa.String(30), nullable=False, server_default="control"),
    )
    op.create_table(
        "runs",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("graph_id", sa.String(100), sa.ForeignKey("pipeline_graphs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("current_node", sa.String(100), nullable=True),
        sa.Column("terminal_reason", sa.String(500), nullable=True),
        sa.Column("metadata", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_pipeline_nodes_graph_id", "pipeline_nodes", ["graph_id"])
    op.create_index("ix_pipeline_edges_graph_id", "pipeline_edges", ["graph_id"])
    op.create_index("ix_runs_graph_id", "runs", ["graph_id"])
    op.create_index("ix_runs_state", "runs", ["state"])


def downgrade() -> None:
    op.drop_index("ix_runs_state", table_name="runs")
    op.drop_index("ix_runs_graph_id", table_name="runs")
    op.drop_index("ix_pipeline_edges_graph_id", table_name="pipeline_edges")
    op.drop_index("ix_pipeline_nodes_graph_id", table_name="pipeline_nodes")
    op.drop_table("runs")
    op.drop_table("pipeline_edges")
    op.drop_table("pipeline_nodes")
    op.drop_table("pipeline_graphs")
