"""S1-02: Add CASCADE DELETE constraints and dependency type validation."""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260329_s1_cascade_and_constraints"
down_revision = "20251207_init_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add CASCADE DELETE to foreign keys and add CHECK constraint on dependency_type."""
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        # PostgreSQL: Use raw SQL for efficient ALTER TABLE statements
        upgrade_postgresql()
    else:
        # SQLite: Use batch_alter_table for compatibility
        upgrade_sqlite()


def upgrade_postgresql() -> None:
    """PostgreSQL-specific upgrade using raw SQL."""
    # Add CHECK constraint on task_dependency.dependency_type
    op.execute("""
        ALTER TABLE task_dependency
        ADD CONSTRAINT check_dependency_type
        CHECK (dependency_type IN ('blocks', 'FINISH_START', 'depends_on'))
    """)

    # Add server default to dependency_type
    op.execute("""
        ALTER TABLE task_dependency
        ALTER COLUMN dependency_type SET DEFAULT 'blocks'
    """)

    # Drop and recreate foreign keys for task_dependency with CASCADE
    op.execute("""
        ALTER TABLE task_dependency
        DROP CONSTRAINT task_dependency_from_id_fkey
    """)
    op.execute("""
        ALTER TABLE task_dependency
        ADD CONSTRAINT task_dependency_from_id_fkey
        FOREIGN KEY (from_id) REFERENCES task(id) ON DELETE CASCADE
    """)

    op.execute("""
        ALTER TABLE task_dependency
        DROP CONSTRAINT task_dependency_to_id_fkey
    """)
    op.execute("""
        ALTER TABLE task_dependency
        ADD CONSTRAINT task_dependency_to_id_fkey
        FOREIGN KEY (to_id) REFERENCES task(id) ON DELETE CASCADE
    """)

    # Add CASCADE to purpose foreign keys
    op.execute("""
        ALTER TABLE purpose
        DROP CONSTRAINT purpose_tenant_id_fkey
    """)
    op.execute("""
        ALTER TABLE purpose
        ADD CONSTRAINT purpose_tenant_id_fkey
        FOREIGN KEY (tenant_id) REFERENCES tenant(id) ON DELETE CASCADE
    """)

    # Add CASCADE to task foreign keys
    op.execute("""
        ALTER TABLE task
        DROP CONSTRAINT task_tenant_id_fkey
    """)
    op.execute("""
        ALTER TABLE task
        ADD CONSTRAINT task_tenant_id_fkey
        FOREIGN KEY (tenant_id) REFERENCES tenant(id) ON DELETE CASCADE
    """)

    op.execute("""
        ALTER TABLE task
        DROP CONSTRAINT task_purpose_id_fkey
    """)
    op.execute("""
        ALTER TABLE task
        ADD CONSTRAINT task_purpose_id_fkey
        FOREIGN KEY (purpose_id) REFERENCES purpose(id) ON DELETE CASCADE
    """)

    # Add CASCADE to feedback foreign keys
    op.execute("""
        ALTER TABLE feedback
        DROP CONSTRAINT feedback_tenant_id_fkey
    """)
    op.execute("""
        ALTER TABLE feedback
        ADD CONSTRAINT feedback_tenant_id_fkey
        FOREIGN KEY (tenant_id) REFERENCES tenant(id) ON DELETE CASCADE
    """)

    op.execute("""
        ALTER TABLE feedback
        DROP CONSTRAINT feedback_purpose_id_fkey
    """)
    op.execute("""
        ALTER TABLE feedback
        ADD CONSTRAINT feedback_purpose_id_fkey
        FOREIGN KEY (purpose_id) REFERENCES purpose(id) ON DELETE CASCADE
    """)

    # Add CASCADE to chatmessage foreign keys
    op.execute("""
        ALTER TABLE chatmessage
        DROP CONSTRAINT chatmessage_tenant_id_fkey
    """)
    op.execute("""
        ALTER TABLE chatmessage
        ADD CONSTRAINT chatmessage_tenant_id_fkey
        FOREIGN KEY (tenant_id) REFERENCES tenant(id) ON DELETE CASCADE
    """)

    op.execute("""
        ALTER TABLE chatmessage
        DROP CONSTRAINT chatmessage_purpose_id_fkey
    """)
    op.execute("""
        ALTER TABLE chatmessage
        ADD CONSTRAINT chatmessage_purpose_id_fkey
        FOREIGN KEY (purpose_id) REFERENCES purpose(id) ON DELETE CASCADE
    """)

    op.execute("""
        ALTER TABLE chatmessage
        DROP CONSTRAINT chatmessage_task_id_fkey
    """)
    op.execute("""
        ALTER TABLE chatmessage
        ADD CONSTRAINT chatmessage_task_id_fkey
        FOREIGN KEY (task_id) REFERENCES task(id) ON DELETE CASCADE
    """)

    op.execute("""
        ALTER TABLE chatmessage
        DROP CONSTRAINT chatmessage_artifact_id_fkey
    """)
    op.execute("""
        ALTER TABLE chatmessage
        ADD CONSTRAINT chatmessage_artifact_id_fkey
        FOREIGN KEY (artifact_id) REFERENCES artifact(id) ON DELETE CASCADE
    """)

    # Add CASCADE to artifact.task_id
    op.execute("""
        ALTER TABLE artifact
        DROP CONSTRAINT artifact_task_id_fkey
    """)
    op.execute("""
        ALTER TABLE artifact
        ADD CONSTRAINT artifact_task_id_fkey
        FOREIGN KEY (task_id) REFERENCES task(id) ON DELETE CASCADE
    """)

    # Add CASCADE to chatmessageartifact foreign keys
    op.execute("""
        ALTER TABLE chatmessageartifact
        DROP CONSTRAINT chatmessageartifact_chat_message_id_fkey
    """)
    op.execute("""
        ALTER TABLE chatmessageartifact
        ADD CONSTRAINT chatmessageartifact_chat_message_id_fkey
        FOREIGN KEY (chat_message_id) REFERENCES chatmessage(id) ON DELETE CASCADE
    """)

    op.execute("""
        ALTER TABLE chatmessageartifact
        DROP CONSTRAINT chatmessageartifact_artifact_id_fkey
    """)
    op.execute("""
        ALTER TABLE chatmessageartifact
        ADD CONSTRAINT chatmessageartifact_artifact_id_fkey
        FOREIGN KEY (artifact_id) REFERENCES artifact(id) ON DELETE CASCADE
    """)

    # Add CASCADE to pipeline_template.tenant_id
    op.execute("""
        ALTER TABLE pipeline_template
        DROP CONSTRAINT pipeline_template_tenant_id_fkey
    """)
    op.execute("""
        ALTER TABLE pipeline_template
        ADD CONSTRAINT pipeline_template_tenant_id_fkey
        FOREIGN KEY (tenant_id) REFERENCES tenant(id) ON DELETE CASCADE
    """)

    # Add CASCADE to tenant_prompt_assignment.tenant_id
    op.execute("""
        ALTER TABLE tenant_prompt_assignment
        DROP CONSTRAINT tenant_prompt_assignment_tenant_id_fkey
    """)
    op.execute("""
        ALTER TABLE tenant_prompt_assignment
        ADD CONSTRAINT tenant_prompt_assignment_tenant_id_fkey
        FOREIGN KEY (tenant_id) REFERENCES tenant(id) ON DELETE CASCADE
    """)

    # Add CASCADE to chatthreadcontext.purpose_id
    op.execute("""
        ALTER TABLE chatthreadcontext
        DROP CONSTRAINT chatthreadcontext_purpose_id_fkey
    """)
    op.execute("""
        ALTER TABLE chatthreadcontext
        ADD CONSTRAINT chatthreadcontext_purpose_id_fkey
        FOREIGN KEY (purpose_id) REFERENCES purpose(id) ON DELETE CASCADE
    """)


def upgrade_sqlite() -> None:
    """SQLite-specific upgrade using batch_alter_table."""

    # task_dependency: Add CASCADE to from_id and to_id
    with op.batch_alter_table("task_dependency", schema=None) as batch_op:
        batch_op.drop_constraint("task_dependency_from_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "task_dependency_from_id_fkey",
            "task",
            ["from_id"],
            ["id"],
            ondelete="CASCADE"
        )

    with op.batch_alter_table("task_dependency", schema=None) as batch_op:
        batch_op.drop_constraint("task_dependency_to_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "task_dependency_to_id_fkey",
            "task",
            ["to_id"],
            ["id"],
            ondelete="CASCADE"
        )

    # Add CHECK constraint and server default to dependency_type
    with op.batch_alter_table("task_dependency", schema=None) as batch_op:
        batch_op.alter_column(
            "dependency_type",
            existing_type=sa.String(length=50),
            server_default="blocks"
        )

    # purpose: Add CASCADE to tenant_id
    with op.batch_alter_table("purpose", schema=None) as batch_op:
        batch_op.drop_constraint("purpose_tenant_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "purpose_tenant_id_fkey",
            "tenant",
            ["tenant_id"],
            ["id"],
            ondelete="CASCADE"
        )

    # task: Add CASCADE to tenant_id and purpose_id
    with op.batch_alter_table("task", schema=None) as batch_op:
        batch_op.drop_constraint("task_tenant_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "task_tenant_id_fkey",
            "tenant",
            ["tenant_id"],
            ["id"],
            ondelete="CASCADE"
        )

    with op.batch_alter_table("task", schema=None) as batch_op:
        batch_op.drop_constraint("task_purpose_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "task_purpose_id_fkey",
            "purpose",
            ["purpose_id"],
            ["id"],
            ondelete="CASCADE"
        )

    # feedback: Add CASCADE to tenant_id and purpose_id
    with op.batch_alter_table("feedback", schema=None) as batch_op:
        batch_op.drop_constraint("feedback_tenant_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "feedback_tenant_id_fkey",
            "tenant",
            ["tenant_id"],
            ["id"],
            ondelete="CASCADE"
        )

    with op.batch_alter_table("feedback", schema=None) as batch_op:
        batch_op.drop_constraint("feedback_purpose_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "feedback_purpose_id_fkey",
            "purpose",
            ["purpose_id"],
            ["id"],
            ondelete="CASCADE"
        )

    # artifact: Add CASCADE to task_id
    with op.batch_alter_table("artifact", schema=None) as batch_op:
        batch_op.drop_constraint("artifact_task_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "artifact_task_id_fkey",
            "task",
            ["task_id"],
            ["id"],
            ondelete="CASCADE"
        )

    # chatmessage: Add CASCADE to tenant_id, purpose_id, artifact_id, task_id
    with op.batch_alter_table("chatmessage", schema=None) as batch_op:
        batch_op.drop_constraint("chatmessage_tenant_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "chatmessage_tenant_id_fkey",
            "tenant",
            ["tenant_id"],
            ["id"],
            ondelete="CASCADE"
        )

    with op.batch_alter_table("chatmessage", schema=None) as batch_op:
        batch_op.drop_constraint("chatmessage_purpose_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "chatmessage_purpose_id_fkey",
            "purpose",
            ["purpose_id"],
            ["id"],
            ondelete="CASCADE"
        )

    with op.batch_alter_table("chatmessage", schema=None) as batch_op:
        batch_op.drop_constraint("chatmessage_artifact_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "chatmessage_artifact_id_fkey",
            "artifact",
            ["artifact_id"],
            ["id"],
            ondelete="CASCADE"
        )

    with op.batch_alter_table("chatmessage", schema=None) as batch_op:
        batch_op.drop_constraint("chatmessage_task_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "chatmessage_task_id_fkey",
            "task",
            ["task_id"],
            ["id"],
            ondelete="CASCADE"
        )

    # chatmessageartifact: Add CASCADE to both foreign keys
    with op.batch_alter_table("chatmessageartifact", schema=None) as batch_op:
        batch_op.drop_constraint("chatmessageartifact_chat_message_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "chatmessageartifact_chat_message_id_fkey",
            "chatmessage",
            ["chat_message_id"],
            ["id"],
            ondelete="CASCADE"
        )

    with op.batch_alter_table("chatmessageartifact", schema=None) as batch_op:
        batch_op.drop_constraint("chatmessageartifact_artifact_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "chatmessageartifact_artifact_id_fkey",
            "artifact",
            ["artifact_id"],
            ["id"],
            ondelete="CASCADE"
        )

    # pipeline_template: Add CASCADE to tenant_id
    with op.batch_alter_table("pipeline_template", schema=None) as batch_op:
        batch_op.drop_constraint("pipeline_template_tenant_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "pipeline_template_tenant_id_fkey",
            "tenant",
            ["tenant_id"],
            ["id"],
            ondelete="CASCADE"
        )

    # tenant_prompt_assignment: Add CASCADE to tenant_id
    with op.batch_alter_table("tenant_prompt_assignment", schema=None) as batch_op:
        batch_op.drop_constraint("tenant_prompt_assignment_tenant_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "tenant_prompt_assignment_tenant_id_fkey",
            "tenant",
            ["tenant_id"],
            ["id"],
            ondelete="CASCADE"
        )

    # chatthreadcontext: Add CASCADE to purpose_id
    with op.batch_alter_table("chatthreadcontext", schema=None) as batch_op:
        batch_op.drop_constraint("chatthreadcontext_purpose_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "chatthreadcontext_purpose_id_fkey",
            "purpose",
            ["purpose_id"],
            ["id"],
            ondelete="CASCADE"
        )


def downgrade() -> None:
    """Revert CASCADE DELETE constraints and dependency type validation."""
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        downgrade_postgresql()
    else:
        downgrade_sqlite()


def downgrade_postgresql() -> None:
    """PostgreSQL-specific downgrade using raw SQL."""
    # Remove CHECK constraint
    op.execute("""
        ALTER TABLE task_dependency
        DROP CONSTRAINT check_dependency_type
    """)

    # Reset server default
    op.execute("""
        ALTER TABLE task_dependency
        ALTER COLUMN dependency_type DROP DEFAULT
    """)

    # Revert foreign keys to without CASCADE for task_dependency
    op.execute("""
        ALTER TABLE task_dependency
        DROP CONSTRAINT task_dependency_from_id_fkey
    """)
    op.execute("""
        ALTER TABLE task_dependency
        ADD CONSTRAINT task_dependency_from_id_fkey
        FOREIGN KEY (from_id) REFERENCES task(id)
    """)

    op.execute("""
        ALTER TABLE task_dependency
        DROP CONSTRAINT task_dependency_to_id_fkey
    """)
    op.execute("""
        ALTER TABLE task_dependency
        ADD CONSTRAINT task_dependency_to_id_fkey
        FOREIGN KEY (to_id) REFERENCES task(id)
    """)

    # Revert CASCADE for all other tables
    op.execute("""
        ALTER TABLE purpose
        DROP CONSTRAINT purpose_tenant_id_fkey,
        ADD CONSTRAINT purpose_tenant_id_fkey
        FOREIGN KEY (tenant_id) REFERENCES tenant(id)
    """)

    op.execute("""
        ALTER TABLE task
        DROP CONSTRAINT task_tenant_id_fkey,
        ADD CONSTRAINT task_tenant_id_fkey
        FOREIGN KEY (tenant_id) REFERENCES tenant(id)
    """)

    op.execute("""
        ALTER TABLE task
        DROP CONSTRAINT task_purpose_id_fkey,
        ADD CONSTRAINT task_purpose_id_fkey
        FOREIGN KEY (purpose_id) REFERENCES purpose(id)
    """)

    op.execute("""
        ALTER TABLE feedback
        DROP CONSTRAINT feedback_tenant_id_fkey,
        ADD CONSTRAINT feedback_tenant_id_fkey
        FOREIGN KEY (tenant_id) REFERENCES tenant(id)
    """)

    op.execute("""
        ALTER TABLE feedback
        DROP CONSTRAINT feedback_purpose_id_fkey,
        ADD CONSTRAINT feedback_purpose_id_fkey
        FOREIGN KEY (purpose_id) REFERENCES purpose(id)
    """)

    op.execute("""
        ALTER TABLE chatmessage
        DROP CONSTRAINT chatmessage_tenant_id_fkey,
        ADD CONSTRAINT chatmessage_tenant_id_fkey
        FOREIGN KEY (tenant_id) REFERENCES tenant(id)
    """)

    op.execute("""
        ALTER TABLE chatmessage
        DROP CONSTRAINT chatmessage_purpose_id_fkey,
        ADD CONSTRAINT chatmessage_purpose_id_fkey
        FOREIGN KEY (purpose_id) REFERENCES purpose(id)
    """)

    op.execute("""
        ALTER TABLE chatmessage
        DROP CONSTRAINT chatmessage_task_id_fkey,
        ADD CONSTRAINT chatmessage_task_id_fkey
        FOREIGN KEY (task_id) REFERENCES task(id)
    """)

    op.execute("""
        ALTER TABLE chatmessage
        DROP CONSTRAINT chatmessage_artifact_id_fkey,
        ADD CONSTRAINT chatmessage_artifact_id_fkey
        FOREIGN KEY (artifact_id) REFERENCES artifact(id)
    """)

    op.execute("""
        ALTER TABLE artifact
        DROP CONSTRAINT artifact_task_id_fkey,
        ADD CONSTRAINT artifact_task_id_fkey
        FOREIGN KEY (task_id) REFERENCES task(id)
    """)

    op.execute("""
        ALTER TABLE chatmessageartifact
        DROP CONSTRAINT chatmessageartifact_chat_message_id_fkey,
        ADD CONSTRAINT chatmessageartifact_chat_message_id_fkey
        FOREIGN KEY (chat_message_id) REFERENCES chatmessage(id)
    """)

    op.execute("""
        ALTER TABLE chatmessageartifact
        DROP CONSTRAINT chatmessageartifact_artifact_id_fkey,
        ADD CONSTRAINT chatmessageartifact_artifact_id_fkey
        FOREIGN KEY (artifact_id) REFERENCES artifact(id)
    """)

    op.execute("""
        ALTER TABLE pipeline_template
        DROP CONSTRAINT pipeline_template_tenant_id_fkey,
        ADD CONSTRAINT pipeline_template_tenant_id_fkey
        FOREIGN KEY (tenant_id) REFERENCES tenant(id)
    """)

    op.execute("""
        ALTER TABLE tenant_prompt_assignment
        DROP CONSTRAINT tenant_prompt_assignment_tenant_id_fkey,
        ADD CONSTRAINT tenant_prompt_assignment_tenant_id_fkey
        FOREIGN KEY (tenant_id) REFERENCES tenant(id)
    """)

    op.execute("""
        ALTER TABLE chatthreadcontext
        DROP CONSTRAINT chatthreadcontext_purpose_id_fkey,
        ADD CONSTRAINT chatthreadcontext_purpose_id_fkey
        FOREIGN KEY (purpose_id) REFERENCES purpose(id)
    """)


def downgrade_sqlite() -> None:
    """SQLite-specific downgrade using batch_alter_table."""
    # task_dependency: Revert CASCADE
    with op.batch_alter_table("task_dependency", schema=None) as batch_op:
        batch_op.drop_constraint("task_dependency_from_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "task_dependency_from_id_fkey",
            "task",
            ["from_id"],
            ["id"]
        )

    with op.batch_alter_table("task_dependency", schema=None) as batch_op:
        batch_op.drop_constraint("task_dependency_to_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "task_dependency_to_id_fkey",
            "task",
            ["to_id"],
            ["id"]
        )

    # Reset server default
    with op.batch_alter_table("task_dependency", schema=None) as batch_op:
        batch_op.alter_column(
            "dependency_type",
            existing_type=sa.String(length=50),
            server_default=None
        )

    # Revert all CASCADE changes back to non-CASCADE
    with op.batch_alter_table("purpose", schema=None) as batch_op:
        batch_op.drop_constraint("purpose_tenant_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "purpose_tenant_id_fkey",
            "tenant",
            ["tenant_id"],
            ["id"]
        )

    with op.batch_alter_table("task", schema=None) as batch_op:
        batch_op.drop_constraint("task_tenant_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "task_tenant_id_fkey",
            "tenant",
            ["tenant_id"],
            ["id"]
        )

    with op.batch_alter_table("task", schema=None) as batch_op:
        batch_op.drop_constraint("task_purpose_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "task_purpose_id_fkey",
            "purpose",
            ["purpose_id"],
            ["id"]
        )

    with op.batch_alter_table("feedback", schema=None) as batch_op:
        batch_op.drop_constraint("feedback_tenant_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "feedback_tenant_id_fkey",
            "tenant",
            ["tenant_id"],
            ["id"]
        )

    with op.batch_alter_table("feedback", schema=None) as batch_op:
        batch_op.drop_constraint("feedback_purpose_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "feedback_purpose_id_fkey",
            "purpose",
            ["purpose_id"],
            ["id"]
        )

    with op.batch_alter_table("artifact", schema=None) as batch_op:
        batch_op.drop_constraint("artifact_task_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "artifact_task_id_fkey",
            "task",
            ["task_id"],
            ["id"]
        )

    with op.batch_alter_table("chatmessage", schema=None) as batch_op:
        batch_op.drop_constraint("chatmessage_tenant_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "chatmessage_tenant_id_fkey",
            "tenant",
            ["tenant_id"],
            ["id"]
        )

    with op.batch_alter_table("chatmessage", schema=None) as batch_op:
        batch_op.drop_constraint("chatmessage_purpose_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "chatmessage_purpose_id_fkey",
            "purpose",
            ["purpose_id"],
            ["id"]
        )

    with op.batch_alter_table("chatmessage", schema=None) as batch_op:
        batch_op.drop_constraint("chatmessage_artifact_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "chatmessage_artifact_id_fkey",
            "artifact",
            ["artifact_id"],
            ["id"]
        )

    with op.batch_alter_table("chatmessage", schema=None) as batch_op:
        batch_op.drop_constraint("chatmessage_task_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "chatmessage_task_id_fkey",
            "task",
            ["task_id"],
            ["id"]
        )

    with op.batch_alter_table("chatmessageartifact", schema=None) as batch_op:
        batch_op.drop_constraint("chatmessageartifact_chat_message_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "chatmessageartifact_chat_message_id_fkey",
            "chatmessage",
            ["chat_message_id"],
            ["id"]
        )

    with op.batch_alter_table("chatmessageartifact", schema=None) as batch_op:
        batch_op.drop_constraint("chatmessageartifact_artifact_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "chatmessageartifact_artifact_id_fkey",
            "artifact",
            ["artifact_id"],
            ["id"]
        )

    with op.batch_alter_table("pipeline_template", schema=None) as batch_op:
        batch_op.drop_constraint("pipeline_template_tenant_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "pipeline_template_tenant_id_fkey",
            "tenant",
            ["tenant_id"],
            ["id"]
        )

    with op.batch_alter_table("tenant_prompt_assignment", schema=None) as batch_op:
        batch_op.drop_constraint("tenant_prompt_assignment_tenant_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "tenant_prompt_assignment_tenant_id_fkey",
            "tenant",
            ["tenant_id"],
            ["id"]
        )

    with op.batch_alter_table("chatthreadcontext", schema=None) as batch_op:
        batch_op.drop_constraint("chatthreadcontext_purpose_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "chatthreadcontext_purpose_id_fkey",
            "purpose",
            ["purpose_id"],
            ["id"]
        )
