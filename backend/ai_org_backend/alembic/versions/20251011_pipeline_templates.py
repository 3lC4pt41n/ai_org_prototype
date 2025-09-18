"""Introduce pipeline template tables and assign defaults."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "20251011_pipeline_templates"
down_revision = "20250910_add_chat_tables"
branch_labels = None
depends_on = None


def _has_table(insp: sa.Inspector, name: str) -> bool:
    return name in insp.get_table_names()


def _has_column(insp: sa.Inspector, table: str, column: str) -> bool:
    return any(col["name"] == column for col in insp.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if not _has_table(insp, "pipeline_template"):
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

    if not _has_table(insp, "pipeline_phase"):
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
            sa.Column("slug", sa.String(length=64), nullable=False, index=True),
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
            sa.Column("business_value_default", sa.Float(), nullable=False, server_default="1"),
            sa.Column("purpose_relevance_default", sa.Float(), nullable=False, server_default="1"),
            sa.Column("requires_approval", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
    elif not _has_column(insp, "pipeline_phase", "slug"):
        op.add_column(
            "pipeline_phase",
            sa.Column("slug", sa.String(length=64), nullable=True),
        )

        rows = bind.execute(sa.text("SELECT id, name FROM pipeline_phase")).fetchall()
        for row in rows:
            slug = _slugify(row.name)
            bind.execute(
                sa.text("UPDATE pipeline_phase SET slug = :slug WHERE id = :id"),
                {"slug": slug, "id": row.id},
            )
        op.alter_column("pipeline_phase", "slug", nullable=False)

    if not _has_column(insp, "task", "pipeline_phase_id"):
        op.add_column("task", sa.Column("pipeline_phase_id", sa.String(length=8), nullable=True))
    if not _has_column(insp, "task", "agent_role"):
        op.add_column("task", sa.Column("agent_role", sa.String(length=100), nullable=True))
    if not _has_column(insp, "task", "model_name"):
        op.add_column("task", sa.Column("model_name", sa.String(length=255), nullable=True))
    if not _has_column(insp, "task", "prompt_template"):
        op.add_column("task", sa.Column("prompt_template", sa.String(length=255), nullable=True))
    if not _has_column(insp, "task", "requires_approval"):
        op.add_column(
            "task",
            sa.Column("requires_approval", sa.Boolean(), nullable=False, server_default=sa.false()),
        )

    if not _has_column(insp, "purpose", "pipeline_template_id"):
        op.add_column(
            "purpose",
            sa.Column("pipeline_template_id", sa.String(length=8), nullable=True),
        )

    fk_names = {fk["name"] for fk in insp.get_foreign_keys("task")}
    if "task_pipeline_phase_id_fkey" not in fk_names:
        op.create_foreign_key(
            "task_pipeline_phase_id_fkey",
            "task",
            "pipeline_phase",
            ["pipeline_phase_id"],
            ["id"],
            ondelete="SET NULL",
        )

    fk_names = {fk["name"] for fk in insp.get_foreign_keys("purpose")}
    if "purpose_pipeline_template_id_fkey" not in fk_names:
        op.create_foreign_key(
            "purpose_pipeline_template_id_fkey",
            "purpose",
            "pipeline_template",
            ["pipeline_template_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # Populate default template if necessary
    conn = bind
    template_id = None
    default_row = conn.execute(
        sa.text(
            "SELECT id FROM pipeline_template "
            "WHERE tenant_id IS NULL AND is_default = true ORDER BY created_at LIMIT 1"
        )
    ).fetchone()
    if default_row:
        template_id = default_row.id
    else:
        template_id = uuid.uuid4().hex[:8]
        conn.execute(
            sa.text(
                "INSERT INTO pipeline_template (id, name, description, tenant_id, is_default, created_at) "
                "VALUES (:id, :name, :description, NULL, true, :created_at)"
            ),
            {
                "id": template_id,
                "name": "Standard Pipeline",
                "description": "Default orchestrator pipeline",
                "created_at": datetime.utcnow(),
            },
        )

    phase_rows = conn.execute(
        sa.text("SELECT id, slug FROM pipeline_phase WHERE pipeline_template_id = :tid"),
        {"tid": template_id},
    ).fetchall()

    if not phase_rows:
        defaults: list[dict[str, Any]] = [
            {
                "slug": "vision",
                "name": "Vision Document",
                "prompt_template": "vision.j2",
                "model_name": "gpt-4",
                "tokens_plan_default": 2000,
            },
            {
                "slug": "prd",
                "name": "Product Requirements Document",
                "prompt_template": "requirements.j2",
                "model_name": "gpt-4",
                "tokens_plan_default": 3500,
                "depends_on": "vision",
            },
            {
                "slug": "architecture",
                "name": "Architecture Blueprint",
                "prompt_template": "architect.j2",
                "model_name": "gpt-4",
                "tokens_plan_default": 4000,
                "depends_on": "prd",
            },
            {
                "slug": "architecture_review",
                "name": "Architecture & Domain Review",
                "prompt_template": "review.j2",
                "model_name": "gpt-4",
                "tokens_plan_default": 1500,
                "agent_role": "reviewer",
                "requires_approval": True,
                "depends_on": "architecture",
            },
            {
                "slug": "implementation",
                "name": "Implementation Plan",
                "prompt_template": "planner.j2",
                "model_name": "gpt-4",
                "tokens_plan_default": 3000,
                "agent_role": "planner",
                "depends_on": "architecture_review",
            },
        ]
        created: dict[str, str] = {}
        for position, definition in enumerate(defaults, start=1):
            phase_id = uuid.uuid4().hex[:8]
            predecessor_slug = definition.get("depends_on")
            predecessor_id = created.get(predecessor_slug) if predecessor_slug else None
            conn.execute(
                sa.text(
                    "INSERT INTO pipeline_phase (id, pipeline_template_id, name, slug, position, predecessor_id, "
                    "agent_role, prompt_template, model_name, tokens_plan_default, business_value_default, "
                    "purpose_relevance_default, requires_approval, created_at) "
                    "VALUES (:id, :template_id, :name, :slug, :position, :predecessor_id, :agent_role, :prompt_template, "
                    ":model_name, :tokens, 1.0, 1.0, :requires_approval, :created_at)"
                ),
                {
                    "id": phase_id,
                    "template_id": template_id,
                    "name": definition["name"],
                    "slug": definition["slug"],
                    "position": position,
                    "predecessor_id": predecessor_id,
                    "agent_role": definition.get("agent_role"),
                    "prompt_template": definition.get("prompt_template"),
                    "model_name": definition.get("model_name"),
                    "tokens": definition.get("tokens_plan_default", 0),
                    "requires_approval": bool(definition.get("requires_approval", False)),
                    "created_at": datetime.utcnow(),
                },
            )
            created[definition["slug"]] = phase_id
        phase_rows = conn.execute(
            sa.text(
                "SELECT id, slug, name, agent_role, prompt_template, model_name, tokens_plan_default, requires_approval "
                "FROM pipeline_phase WHERE pipeline_template_id = :tid"
            ),
            {"tid": template_id},
        ).fetchall()

    phase_map = {row.slug: row for row in phase_rows}
    if phase_map:
        conn.execute(
            sa.text(
                "UPDATE purpose SET pipeline_template_id = :tid "
                "WHERE pipeline_template_id IS NULL"
            ),
            {"tid": template_id},
        )

        keyword_map = [
            ("architecture & domain review", "architecture_review"),
            ("architecture review", "architecture_review"),
            ("architecture blueprint", "architecture"),
            ("implementation plan", "implementation"),
            ("implementation", "implementation"),
            ("product requirements", "prd"),
            ("prd", "prd"),
            ("vision", "vision"),
        ]
        fallback_phase = next(iter(phase_map.values()))

        tasks = conn.execute(
            sa.text(
                "SELECT id, description, pipeline_phase_id FROM task"
            )
        ).fetchall()
        for task in tasks:
            if task.pipeline_phase_id:
                continue
            desc = (task.description or "").lower()
            target_slug = None
            for keyword, slug in keyword_map:
                if keyword in desc:
                    target_slug = slug
                    break
            if not target_slug:
                target_slug = "vision"
            phase_info = phase_map.get(target_slug, fallback_phase)
            if not phase_info:
                continue
            conn.execute(
                sa.text(
                    "UPDATE task SET pipeline_phase_id = :pid WHERE id = :tid"
                ),
                {"pid": phase_info.id, "tid": task.id},
            )

        for phase in phase_map.values():
            conn.execute(
                sa.text(
                    "UPDATE task SET agent_role = COALESCE(agent_role, :agent_role), "
                    "model_name = COALESCE(model_name, :model_name), "
                    "prompt_template = COALESCE(prompt_template, :prompt_template), "
                    "requires_approval = COALESCE(requires_approval, :requires_approval) "
                    "WHERE pipeline_phase_id = :pid"
                ),
                {
                    "agent_role": phase.agent_role,
                    "model_name": phase.model_name,
                    "prompt_template": phase.prompt_template,
                    "requires_approval": bool(phase.requires_approval),
                    "pid": phase.id,
                },
            )
            conn.execute(
                sa.text(
                    "UPDATE task SET tokens_plan = :tokens "
                    "WHERE pipeline_phase_id = :pid AND COALESCE(tokens_plan, 0) = 0"
                ),
                {"tokens": phase.tokens_plan_default or 0, "pid": phase.id},
            )

    op.alter_column("pipeline_template", "is_default", server_default=None)
    op.alter_column("pipeline_phase", "position", server_default=None)
    op.alter_column("pipeline_phase", "tokens_plan_default", server_default=None)
    op.alter_column("pipeline_phase", "business_value_default", server_default=None)
    op.alter_column("pipeline_phase", "purpose_relevance_default", server_default=None)
    op.alter_column("pipeline_phase", "requires_approval", server_default=None)
    op.alter_column("pipeline_template", "created_at", server_default=None)
    op.alter_column("pipeline_phase", "created_at", server_default=None)
    op.alter_column("task", "requires_approval", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "task_pipeline_phase_id_fkey" in {fk["name"] for fk in insp.get_foreign_keys("task")}:
        op.drop_constraint("task_pipeline_phase_id_fkey", "task", type_="foreignkey")
    if "purpose_pipeline_template_id_fkey" in {fk["name"] for fk in insp.get_foreign_keys("purpose")}:
        op.drop_constraint("purpose_pipeline_template_id_fkey", "purpose", type_="foreignkey")

    if _has_column(insp, "purpose", "pipeline_template_id"):
        op.drop_column("purpose", "pipeline_template_id")
    for column in [
        "requires_approval",
        "prompt_template",
        "model_name",
        "agent_role",
        "pipeline_phase_id",
    ]:
        if _has_column(insp, "task", column):
            op.drop_column("task", column)

    if _has_table(insp, "pipeline_phase"):
        op.drop_table("pipeline_phase")
    if _has_table(insp, "pipeline_template"):
        op.drop_table("pipeline_template")


def _slugify(value: str) -> str:
    value = value.lower().replace("&", " and ")
    value = "".join(ch if ch.isalnum() else "_" for ch in value)
    while "__" in value:
        value = value.replace("__", "_")
    return value.strip("_") or "phase"
