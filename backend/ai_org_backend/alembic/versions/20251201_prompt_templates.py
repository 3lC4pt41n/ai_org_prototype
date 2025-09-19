"""Create prompt template tables and seed defaults."""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "20251201_prompt_templates"
down_revision = "20251011_pipeline_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prompt_template",
        sa.Column("id", sa.String(length=8), primary_key=True),
        sa.Column("phase_slug", sa.String(length=64), nullable=False),
        sa.Column("agent", sa.String(length=100), nullable=True),
        sa.Column("default_path", sa.String(length=255), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tenant_id", sa.String(length=8), sa.ForeignKey("tenant.id"), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_prompt_template_phase_slug",
        "prompt_template",
        ["phase_slug"],
    )

    op.create_table(
        "tenant_prompt_assignment",
        sa.Column("id", sa.String(length=8), primary_key=True),
        sa.Column("tenant_id", sa.String(length=8), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("phase_slug", sa.String(length=64), nullable=False),
        sa.Column(
            "prompt_template_id",
            sa.String(length=8),
            sa.ForeignKey("prompt_template.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_tenant_prompt_assignment_tenant_phase",
        "tenant_prompt_assignment",
        ["tenant_id", "phase_slug"],
        unique=True,
    )

    # Seed the global defaults from the prompts directory when available
    bind = op.get_bind()
    prompts_dir = Path(__file__).resolve().parents[4] / "prompts"
    default_templates = [
        ("vision", "vision.j2"),
        ("prd", "requirements.j2"),
        ("architecture", "architect.j2"),
        ("architecture_review", "review.j2"),
        ("implementation", "planner.j2"),
    ]
    for phase_slug, filename in default_templates:
        existing = bind.execute(
            sa.text(
                "SELECT 1 FROM prompt_template "
                "WHERE tenant_id IS NULL AND phase_slug = :slug LIMIT 1"
            ),
            {"slug": phase_slug},
        ).fetchone()
        if existing:
            continue
        content = ""
        file_path = prompts_dir / filename
        if file_path.exists():
            try:
                content = file_path.read_text(encoding="utf-8")
            except Exception:
                content = ""
        bind.execute(
            sa.text(
                "INSERT INTO prompt_template "
                "(id, phase_slug, agent, default_path, created_by, content, tenant_id, created_at) "
                "VALUES (:id, :slug, NULL, :path, NULL, :content, NULL, :created_at)"
            ),
            {
                "id": uuid.uuid4().hex[:8],
                "slug": phase_slug,
                "path": filename,
                "content": content,
                "created_at": datetime.utcnow(),
            },
        )


def downgrade() -> None:
    op.drop_index(
        "ix_tenant_prompt_assignment_tenant_phase",
        table_name="tenant_prompt_assignment",
    )
    op.drop_table("tenant_prompt_assignment")
    op.drop_index("ix_prompt_template_phase_slug", table_name="prompt_template")
    op.drop_table("prompt_template")
