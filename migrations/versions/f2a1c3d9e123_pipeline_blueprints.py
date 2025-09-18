"""create pipeline template tables"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from alembic import op


revision = "f2a1c3d9e123"
down_revision = "0a1e1fb0dca64e9c96b8fc5f1a8e3b12"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pipeline_template",
        sa.Column("id", sa.String(length=8), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "pipeline_phase",
        sa.Column("id", sa.String(length=8), primary_key=True),
        sa.Column(
            "pipeline_template_id",
            sa.String(length=8),
            sa.ForeignKey("pipeline_template.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "predecessor_id",
            sa.String(length=8),
            sa.ForeignKey("pipeline_phase.id"),
            nullable=True,
        ),
        sa.Column("agent_role", sa.String(length=100), nullable=True),
        sa.Column("prompt_template", sa.String(length=255), nullable=True),
        sa.Column("model_name", sa.String(length=255), nullable=True),
        sa.Column("tokens_plan_default", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "business_value_default",
            sa.Float(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "purpose_relevance_default",
            sa.Float(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "requires_approval",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.add_column(
        "task",
        sa.Column("pipeline_phase_id", sa.String(length=8), nullable=True),
    )
    op.add_column(
        "task",
        sa.Column("agent_role", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "task",
        sa.Column("model_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "task",
        sa.Column("prompt_template", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "task",
        sa.Column(
            "requires_approval",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    op.add_column(
        "purpose",
        sa.Column("pipeline_template_id", sa.String(length=8), nullable=True),
    )

    op.create_foreign_key(
        "task_pipeline_phase_id_fkey",
        "task",
        "pipeline_phase",
        ["pipeline_phase_id"],
        ["id"],
    )
    op.create_foreign_key(
        "purpose_pipeline_template_id_fkey",
        "purpose",
        "pipeline_template",
        ["pipeline_template_id"],
        ["id"],
    )

    op.alter_column(
        "pipeline_template",
        "is_default",
        server_default=None,
        existing_type=sa.Boolean(),
    )
    op.alter_column(
        "pipeline_phase",
        "position",
        server_default=None,
        existing_type=sa.Integer(),
    )
    op.alter_column(
        "pipeline_phase",
        "tokens_plan_default",
        server_default=None,
        existing_type=sa.Integer(),
    )
    op.alter_column(
        "pipeline_phase",
        "business_value_default",
        server_default=None,
        existing_type=sa.Float(),
    )
    op.alter_column(
        "pipeline_phase",
        "purpose_relevance_default",
        server_default=None,
        existing_type=sa.Float(),
    )
    op.alter_column(
        "pipeline_phase",
        "requires_approval",
        server_default=None,
        existing_type=sa.Boolean(),
    )
    op.alter_column(
        "pipeline_template",
        "created_at",
        server_default=None,
        existing_type=sa.DateTime(timezone=True),
    )
    op.alter_column(
        "pipeline_phase",
        "created_at",
        server_default=None,
        existing_type=sa.DateTime(timezone=True),
    )
    op.alter_column(
        "task",
        "requires_approval",
        server_default=None,
        existing_type=sa.Boolean(),
    )

    template_id = uuid.uuid4().hex[:8]
    phase_ids = [uuid.uuid4().hex[:8] for _ in range(5)]
    now = datetime.utcnow()

    op.bulk_insert(
        sa.table(
            "pipeline_template",
            sa.column("id", sa.String(length=8)),
            sa.column("name", sa.String(length=255)),
            sa.column("description", sa.Text()),
            sa.column("tenant_id", sa.String()),
            sa.column("is_default", sa.Boolean()),
            sa.column("created_at", sa.DateTime(timezone=True)),
        ),
        [
            {
                "id": template_id,
                "name": "Standard Pipeline",
                "description": "Default orchestrator pipeline",
                "tenant_id": None,
                "is_default": True,
                "created_at": now,
            }
        ],
    )

    phase_rows = []
    defaults = [
        ("Vision Document", None, None, "vision.j2", "gpt-4", 2000, 1.0, 1.0, False),
        (
            "Product Requirements Document",
            0,
            None,
            "requirements.j2",
            "gpt-4",
            3500,
            1.0,
            1.0,
            False,
        ),
        (
            "Architecture Blueprint",
            1,
            None,
            "architect.j2",
            "gpt-4",
            4000,
            1.0,
            1.0,
            False,
        ),
        (
            "Architecture & Domain Review",
            2,
            "reviewer",
            "review.j2",
            "gpt-4",
            1500,
            1.0,
            1.0,
            True,
        ),
        (
            "Implementation Plan",
            3,
            "planner",
            "planner.j2",
            "gpt-4",
            3000,
            1.0,
            1.0,
            False,
        ),
    ]

    for idx, phase_id in enumerate(phase_ids):
        name, predecessor_index, role, prompt, model, tokens, bv, relevance, approval = defaults[idx]
        phase_rows.append(
            {
                "id": phase_id,
                "pipeline_template_id": template_id,
                "name": name,
                "position": idx + 1,
                "predecessor_id": phase_ids[predecessor_index] if predecessor_index is not None else None,
                "agent_role": role,
                "prompt_template": prompt,
                "model_name": model,
                "tokens_plan_default": tokens,
                "business_value_default": bv,
                "purpose_relevance_default": relevance,
                "requires_approval": approval,
                "created_at": now,
            }
        )

    op.bulk_insert(
        sa.table(
            "pipeline_phase",
            sa.column("id", sa.String(length=8)),
            sa.column("pipeline_template_id", sa.String(length=8)),
            sa.column("name", sa.String(length=255)),
            sa.column("position", sa.Integer()),
            sa.column("predecessor_id", sa.String(length=8)),
            sa.column("agent_role", sa.String(length=100)),
            sa.column("prompt_template", sa.String(length=255)),
            sa.column("model_name", sa.String(length=255)),
            sa.column("tokens_plan_default", sa.Integer()),
            sa.column("business_value_default", sa.Float()),
            sa.column("purpose_relevance_default", sa.Float()),
            sa.column("requires_approval", sa.Boolean()),
            sa.column("created_at", sa.DateTime(timezone=True)),
        ),
        phase_rows,
    )


def downgrade() -> None:
    op.drop_constraint("task_pipeline_phase_id_fkey", "task", type_="foreignkey")
    op.drop_constraint(
        "purpose_pipeline_template_id_fkey", "purpose", type_="foreignkey"
    )
    op.drop_column("purpose", "pipeline_template_id")
    op.drop_column("task", "requires_approval")
    op.drop_column("task", "prompt_template")
    op.drop_column("task", "model_name")
    op.drop_column("task", "agent_role")
    op.drop_column("task", "pipeline_phase_id")
    op.drop_table("pipeline_phase")
    op.drop_table("pipeline_template")
