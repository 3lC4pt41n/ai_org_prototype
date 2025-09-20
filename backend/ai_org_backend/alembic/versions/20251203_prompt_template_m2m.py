"""Move prompt template tenant link to association table."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "20251203_prompt_template_m2m"
down_revision = "20251202_merge_pipeline_prompt_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    existing_pairs = {
        (row.tenant_id, row.phase_slug)
        for row in conn.execute(
            sa.text(
                "SELECT tenant_id, phase_slug FROM tenant_prompt_assignment"
            )
        ).fetchall()
    }

    templates = conn.execute(
        sa.text(
            "SELECT id, tenant_id, phase_slug, created_by "
            "FROM prompt_template WHERE tenant_id IS NOT NULL"
        )
    ).fetchall()

    for template_id, tenant_id, phase_slug, created_by in templates:
        if tenant_id is None:
            continue
        if (tenant_id, phase_slug) not in existing_pairs:
            conn.execute(
                sa.text(
                    "INSERT INTO tenant_prompt_assignment "
                    "(id, tenant_id, phase_slug, prompt_template_id, created_at) "
                    "VALUES (:id, :tenant_id, :phase_slug, :prompt_template_id, :created_at)"
                ),
                {
                    "id": uuid.uuid4().hex[:8],
                    "tenant_id": tenant_id,
                    "phase_slug": phase_slug,
                    "prompt_template_id": template_id,
                    "created_at": datetime.utcnow(),
                },
            )
            existing_pairs.add((tenant_id, phase_slug))

        if not created_by:
            conn.execute(
                sa.text(
                    "UPDATE prompt_template SET created_by = :created_by WHERE id = :id"
                ),
                {"created_by": tenant_id, "id": template_id},
            )

    op.drop_constraint(
        "prompt_template_tenant_id_fkey",
        "prompt_template",
        type_="foreignkey",
    )
    op.drop_column("prompt_template", "tenant_id")


def downgrade() -> None:
    op.add_column(
        "prompt_template",
        sa.Column("tenant_id", sa.String(length=8), nullable=True),
    )
    op.create_foreign_key(
        "prompt_template_tenant_id_fkey",
        "prompt_template",
        "tenant",
        ["tenant_id"],
        ["id"],
    )

    conn = op.get_bind()
    assignments = conn.execute(
        sa.text(
            "SELECT tenant_id, prompt_template_id FROM tenant_prompt_assignment"
        )
    ).fetchall()

    for tenant_id, template_id in assignments:
        if tenant_id is None or template_id is None:
            continue
        conn.execute(
            sa.text(
                "UPDATE prompt_template SET tenant_id = :tenant_id "
                "WHERE id = :template_id AND tenant_id IS NULL"
            ),
            {"tenant_id": tenant_id, "template_id": template_id},
        )

    conn.execute(
        sa.text(
            "UPDATE prompt_template SET created_by = NULL "
            "WHERE tenant_id IS NOT NULL AND created_by = tenant_id"
        )
    )
