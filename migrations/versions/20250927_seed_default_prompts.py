"""Seed default prompt templates into DB from /app/prompts"""

from __future__ import annotations

import os
from pathlib import Path

from alembic import op
import sqlalchemy as sa

# Revision identifiers, used by Alembic.
revision = "20250927_seed_default_prompts"
down_revision = "20251202_merge_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    prompts_dir = Path(os.environ.get("PROMPTS_DIR", "/app/prompts"))

    files = {
        "vision": "vision.j2",
        "prd": "requirements.j2",
        "architecture": "architect.j2",
        "architecture_review": "review.j2",
        "implementation": "planner.j2",
    }

    for phase_slug, filename in files.items():
        file_path = prompts_dir / filename
        if not file_path.exists():
            print(f"[WARN] Prompt file missing: {file_path}")
            continue

        content = file_path.read_text(encoding="utf-8")

        exists = conn.execute(
            sa.text(
                "SELECT 1 FROM prompt_template WHERE phase_slug=:phase AND default_path=:path"
            ),
            {"phase": phase_slug, "path": filename},
        ).first()

        if not exists:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO prompt_template (phase_slug, default_path, content, created_by)
                    VALUES (:phase, :path, :content, NULL)
                    """
                ),
                {"phase": phase_slug, "path": filename, "content": content},
            )
            print(f"[INFO] Seeded prompt: {filename} -> phase {phase_slug}")


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            DELETE FROM prompt_template
            WHERE default_path IN ('vision.j2','requirements.j2','architect.j2','review.j2','planner.j2')
            """
        )
    )
