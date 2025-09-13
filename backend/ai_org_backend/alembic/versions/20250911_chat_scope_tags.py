"""Add chat scope/intent fields and ChatMessageArtifact table.

Revision ID: 20250911_chat_scope_tags
Revises: a5099ac4bc8e
Create Date: 2025-09-11 23:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# Revision identifiers, used by Alembic.
revision: str = "20250911_chat_scope_tags"
down_revision: Union[str, Sequence[str], None] = "a5099ac4bc8e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    # 1. Add new columns scope and intent to chatmessage (with default for existing data)
    op.add_column(
        "chatmessage",
        sa.Column(
            "scope",
            sa.Enum("global", "artifact", "mixed", name="chatscope"),
            nullable=False,
            server_default="global",
        ),
    )
    op.add_column(
        "chatmessage",
        sa.Column(
            "intent",
            sa.Enum("question", "feedback", "note", "approval", name="chatintent"),
            nullable=False,
            server_default="question",
        ),
    )
    # 2. Create chatmessageartifact join table
    if not insp.has_table("chatmessageartifact"):
        op.create_table(
            "chatmessageartifact",
            sa.Column(
                "chat_message_id",
                sa.String(),
                sa.ForeignKey("chatmessage.id"),
                nullable=False,
            ),
            sa.Column(
                "artifact_id",
                sa.String(),
                sa.ForeignKey("artifact.id"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("chat_message_id", "artifact_id"),
        )
    # 3. Migrate existing data: set scope for old messages and create join entries
    op.execute("UPDATE chatmessage SET scope='artifact' WHERE artifact_id IS NOT NULL;")
    op.execute(
        "INSERT INTO chatmessageartifact (chat_message_id, artifact_id) "
        "SELECT id, artifact_id FROM chatmessage WHERE artifact_id IS NOT NULL;"
    )
    op.execute("UPDATE chatmessage SET intent='note' WHERE role IN ('assistant', 'agent');")
    # 4. Remove default values
    op.alter_column("chatmessage", "scope", server_default=None)
    op.alter_column("chatmessage", "intent", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    # 1. Drop join table
    if insp.has_table("chatmessageartifact"):
        op.drop_table("chatmessageartifact")
    # 2. Drop new columns and enums
    op.drop_column("chatmessage", "scope")
    op.drop_column("chatmessage", "intent")
    op.execute("DROP TYPE IF EXISTS chatscope")
    op.execute("DROP TYPE IF EXISTS chatintent")
