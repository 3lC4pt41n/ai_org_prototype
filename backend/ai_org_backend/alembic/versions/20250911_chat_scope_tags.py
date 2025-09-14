"""Add chat scope/intent fields and ChatMessageArtifact table.

Revision ID: 20250911_chat_scope_tags
Revises: b7ac9e1dd64e
Create Date: 2025-09-11 23:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# Revision identifiers, used by Alembic.
revision: str = "20250911_chat_scope_tags"
down_revision: Union[str, Sequence[str], None] = "b7ac9e1dd64e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1. Create Enum types first
    chatscope_enum = sa.Enum("global", "artifact", "mixed", name="chatscope")
    chatintent_enum = sa.Enum("question", "feedback", "note", "approval", name="chatintent")
    chatscope_enum.create(bind, checkfirst=True)
    chatintent_enum.create(bind, checkfirst=True)

    # 2. Add new columns using the created enums
    op.add_column(
        "chatmessage",
        sa.Column("scope", chatscope_enum, nullable=False, server_default="global"),
    )
    op.add_column(
        "chatmessage",
        sa.Column("intent", chatintent_enum, nullable=False, server_default="question"),
    )

    # 3. Create join table if not exists
    if not insp.has_table("chatmessageartifact"):
        op.create_table(
            "chatmessageartifact",
            sa.Column("chat_message_id", sa.String(), sa.ForeignKey("chatmessage.id"), nullable=False),
            sa.Column("artifact_id", sa.String(), sa.ForeignKey("artifact.id"), nullable=False),
            sa.PrimaryKeyConstraint("chat_message_id", "artifact_id"),
        )

    # 4. Optional: migrate existing data
    op.execute("UPDATE chatmessage SET scope='artifact' WHERE artifact_id IS NOT NULL;")
    op.execute("INSERT INTO chatmessageartifact (chat_message_id, artifact_id) "
               "SELECT id, artifact_id FROM chatmessage WHERE artifact_id IS NOT NULL;")
    op.execute("UPDATE chatmessage SET intent='note' WHERE role IN ('assistant', 'agent');")

    # 5. Remove server defaults
    op.alter_column("chatmessage", "scope", server_default=None)
    op.alter_column("chatmessage", "intent", server_default=None)


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if insp.has_table("chatmessageartifact"):
        op.drop_table("chatmessageartifact")
    op.drop_column("chatmessage", "scope")
    op.drop_column("chatmessage", "intent")

    # Drop enum types
    sa.Enum(name="chatscope").drop(bind, checkfirst=True)
    sa.Enum(name="chatintent").drop(bind, checkfirst=True)
