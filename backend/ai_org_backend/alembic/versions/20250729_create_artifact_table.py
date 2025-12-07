"""add artifact table

Revision ID: 20250729_create_artifact_table
Revises: 1b8ce9772b4a
Create Date: 2025-07-29 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# Revision identifiers, used by Alembic.
revision: str = "20250729_create_artifact_table"
down_revision: Union[str, Sequence[str], None] = "1b8ce9772b4a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema by creating the artifact table."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    # Vorhandene alte Tabelle (plural) umbenennen, falls nötig
    if insp.has_table("artifacts") and not insp.has_table("artifact"):
        op.rename_table("artifacts", "artifact")
    # Tabelle erstellen, wenn sie noch nicht existiert
    if not insp.has_table("artifact"):
        op.create_table(
            "artifact",
            sa.Column("id", sa.String(), primary_key=True, nullable=False),
            sa.Column("task_id", sa.String(), sa.ForeignKey("task.id"), nullable=False),
            sa.Column("repo_path", sa.String(), nullable=False),
            sa.Column("media_type", sa.String(), nullable=False),
            sa.Column("size", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("sha256", sa.String(length=64), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
        # Standardwerte nach Initialisierung entfernen
        op.alter_column("artifact", "size", server_default=None)
        op.alter_column("artifact", "created_at", server_default=None)


def downgrade() -> None:
    """Downgrade schema by dropping the artifact table."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if insp.has_table("artifact"):
        op.drop_table("artifact")
