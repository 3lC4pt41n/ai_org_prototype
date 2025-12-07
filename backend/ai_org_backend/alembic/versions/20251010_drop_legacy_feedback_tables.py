"""Drop legacy feedback tables."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20251010_drop_legacy_feedback_tables"
down_revision: Union[str, Sequence[str], None] = "20250729_create_artifact_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop legacy feedback tables when they still exist."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())
    for table_name in ("feedback", "artifactfeedback"):
        if table_name in existing_tables:
            op.drop_table(table_name)


def downgrade() -> None:
    """No downgrade step; legacy tables are not restored."""
    pass
