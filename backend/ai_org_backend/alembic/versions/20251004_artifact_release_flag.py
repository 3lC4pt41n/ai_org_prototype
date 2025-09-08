"""Add released flag to Artifact and drop approved from ArtifactFeedback"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# Revision identifiers, used by Alembic.
revision: str = "20251004_artifact_release_flag"
down_revision: Union[str, Sequence[str], None] = "d27cd98b999b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # Add 'released' to artifact
    if insp.has_table("artifact") and not insp.has_column("artifact", "released"):
        op.add_column(
            "artifact",
            sa.Column("released", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        # remove server_default so ORM doesn’t always insert explicitly
        op.alter_column("artifact", "released", server_default=None)

    # Drop 'approved' from artifactfeedback
    if insp.has_table("artifactfeedback"):
        cols = [c["name"] for c in insp.get_columns("artifactfeedback")]
        if "approved" in cols:
            op.drop_column("artifactfeedback", "approved")


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # Re-add 'approved' to artifactfeedback
    if insp.has_table("artifactfeedback"):
        cols = [c["name"] for c in insp.get_columns("artifactfeedback")]
        if "approved" not in cols:
            op.add_column(
                "artifactfeedback",
                sa.Column("approved", sa.Boolean(), nullable=False, server_default=sa.false()),
            )
            op.alter_column("artifactfeedback", "approved", server_default=None)

    # Drop 'released' from artifact
    if insp.has_table("artifact") and insp.has_column("artifact", "released"):
        op.drop_column("artifact", "released")
