"""Add released flag to Artifact and drop approved from ArtifactFeedback"""

from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "20251004_artifact_release_flag"
down_revision: Union[str, Sequence[str], None] = "d27cd98b999b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(insp, name: str) -> bool:
    return name in insp.get_table_names()

def _has_column(insp, table: str, col: str) -> bool:
    return any(c["name"] == col for c in insp.get_columns(table))

def _resolve_table(insp, candidates: list[str]) -> Union[str, None]:
    """Return the first candidate that exists, else None."""
    names = set(insp.get_table_names())
    for c in candidates:
        if c in names:
            return c
    return None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # --- Artifact.released (BOOLEAN NOT NULL DEFAULT false) ---
    artifact_tbl = _resolve_table(insp, ["artifact", "artifacts"])
    if artifact_tbl and not _has_column(insp, artifact_tbl, "released"):
        op.add_column(
            artifact_tbl,
            sa.Column(
                "released",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),  # Postgres-safe default
            ),
        )
        # drop default after backfilling existing rows
        op.alter_column(artifact_tbl, "released", server_default=None)

    # --- Drop ArtifactFeedback.approved ---
    af_tbl = _resolve_table(insp, ["artifactfeedback", "artifact_feedback"])
    if af_tbl and _has_column(insp, af_tbl, "approved"):
        op.drop_column(af_tbl, "approved")


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # --- Re-add ArtifactFeedback.approved ---
    af_tbl = _resolve_table(insp, ["artifactfeedback", "artifact_feedback"])
    if af_tbl and not _has_column(insp, af_tbl, "approved"):
        op.add_column(
            af_tbl,
            sa.Column(
                "approved",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )
        op.alter_column(af_tbl, "approved", server_default=None)

    # --- Drop Artifact.released ---
    artifact_tbl = _resolve_table(insp, ["artifact", "artifacts"])
    if artifact_tbl and _has_column(insp, artifact_tbl, "released"):
        op.drop_column(artifact_tbl, "released")
