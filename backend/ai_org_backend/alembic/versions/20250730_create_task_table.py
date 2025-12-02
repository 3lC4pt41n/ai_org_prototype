"""Create task table to match SQLModel Task definition."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20250730_create_task_table"
down_revision: Union[str, Sequence[str], None] = "1b8ce9772b4a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _task_columns(insp: sa.Inspector) -> list[sa.Column]:
    """Build task column definitions, guarding FKs for optional tables."""

    columns: list[sa.Column] = [
        sa.Column("id", sa.String(length=8), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False),
    ]

    if insp.has_table("purpose"):
        columns.append(
            sa.Column(
                "purpose_id",
                sa.String(length=8),
                sa.ForeignKey("purpose.id"),
                nullable=True,
            )
        )
    else:
        columns.append(sa.Column("purpose_id", sa.String(length=8), nullable=True))

    if insp.has_table("pipeline_phase"):
        columns.append(
            sa.Column(
                "pipeline_phase_id",
                sa.String(length=8),
                sa.ForeignKey("pipeline_phase.id"),
                nullable=True,
            )
        )
    else:
        columns.append(sa.Column("pipeline_phase_id", sa.String(length=8), nullable=True))

    columns.extend(
        [
            sa.Column("description", sa.String(length=2000), nullable=False),
            sa.Column(
                "business_value",
                sa.Float(),
                nullable=False,
                server_default=sa.text("1.0"),
            ),
            sa.Column(
                "tokens_plan", sa.Integer(), nullable=False, server_default=sa.text("0")
            ),
            sa.Column(
                "tokens_actual", sa.Integer(), nullable=False, server_default=sa.text("0")
            ),
            sa.Column(
                "purpose_relevance",
                sa.Float(),
                nullable=False,
                server_default=sa.text("0.0"),
            ),
            sa.Column("agent_role", sa.String(length=100), nullable=True),
            sa.Column("model_name", sa.String(length=255), nullable=True),
            sa.Column("prompt_template", sa.String(length=255), nullable=True),
            sa.Column(
                "requires_approval",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column("status", sa.String(), nullable=False, server_default="todo"),
            sa.Column("owner", sa.String(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=False, server_default=sa.text("''")),
            sa.Column("retries", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        ]
    )

    return columns


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if insp.has_table("task"):
        return

    op.create_table("task", *_task_columns(insp))

    for column in [
        "business_value",
        "tokens_plan",
        "tokens_actual",
        "purpose_relevance",
        "requires_approval",
        "status",
        "notes",
        "retries",
        "created_at",
    ]:
        op.alter_column("task", column, server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if insp.has_table("task"):
        op.drop_table("task")
