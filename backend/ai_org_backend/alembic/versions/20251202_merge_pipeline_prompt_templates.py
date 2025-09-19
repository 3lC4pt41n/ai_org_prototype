"""Merge pipeline_templates and prompt_templates.

Revision ID: 20251202_merge_pipeline_prompt_templates
Revises: 20251011_pipeline_templates, 20251201_prompt_templates
Create Date: 2025-12-02 00:00:00.000000
"""

from __future__ import annotations

# revision identifiers, used by Alembic.
revision = "20251202_merge_pipeline_prompt_templates"
down_revision = ("20251011_pipeline_templates", "20251201_prompt_templates")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
