"""S3-12: Add version_number and parent_id to Artifact table.

Revision ID: s3_12_artifact_versioning
Revises: s2_03_version_heartbeat
Create Date: 2026-03-29
"""

from alembic import op
import sqlalchemy as sa

revision = "s3_12_artifact_versioning"
down_revision = "s2_03_version_heartbeat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name

    if dialect == "sqlite":
        with op.batch_alter_table("artifact") as batch_op:
            batch_op.add_column(
                sa.Column("version_number", sa.Integer(), nullable=False, server_default="1")
            )
            batch_op.add_column(
                sa.Column("parent_id", sa.String(), nullable=True)
            )
    else:
        op.add_column(
            "artifact",
            sa.Column("version_number", sa.Integer(), nullable=False, server_default="1"),
        )
        op.add_column(
            "artifact",
            sa.Column("parent_id", sa.String(), nullable=True),
        )
        op.create_foreign_key(
            "fk_artifact_parent",
            "artifact", "artifact",
            ["parent_id"], ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    dialect = op.get_bind().dialect.name

    if dialect == "sqlite":
        with op.batch_alter_table("artifact") as batch_op:
            batch_op.drop_column("parent_id")
            batch_op.drop_column("version_number")
    else:
        op.drop_constraint("fk_artifact_parent", "artifact", type_="foreignkey")
        op.drop_column("artifact", "parent_id")
        op.drop_column("artifact", "version_number")
