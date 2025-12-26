"""Initial database schema creation."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20251207_init_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Tenants table
    op.create_table(
        "tenant",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("balance", sa.Float(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("allow_web_research", sa.Boolean(), nullable=False),
        sa.Column("enable_code_review", sa.Boolean(), nullable=False),
        sa.Column("enable_refactor", sa.Boolean(), nullable=False),
        sa.Column(
            "theme",
            sa.Enum("light", "dark", name="usertheme"),
            nullable=False,
            server_default="light",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # Prompt templates table
    op.create_table(
        "prompt_template",
        sa.Column("id", sa.String(length=8), nullable=False),
        sa.Column("phase_slug", sa.String(length=64), nullable=False),
        sa.Column("agent", sa.String(length=100), nullable=True),
        sa.Column("default_path", sa.String(length=255), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    # Pipeline templates and phases
    op.create_table(
        "pipeline_template",
        sa.Column("id", sa.String(length=8), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "pipeline_phase",
        sa.Column("id", sa.String(length=8), nullable=False),
        sa.Column(
            "pipeline_template_id",
            sa.String(),
            sa.ForeignKey("pipeline_template.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "predecessor_id",
            sa.String(),
            sa.ForeignKey("pipeline_phase.id"),
            nullable=True,
        ),
        sa.Column("agent_role", sa.String(length=100), nullable=True),
        sa.Column("prompt_template", sa.String(length=255), nullable=True),
        sa.Column("model_name", sa.String(length=255), nullable=True),
        sa.Column("tokens_plan_default", sa.Integer(), nullable=False),
        sa.Column("business_value_default", sa.Float(), nullable=False),
        sa.Column("purpose_relevance_default", sa.Float(), nullable=False),
        sa.Column("requires_approval", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    # Purposes table
    op.create_table(
        "purpose",
        sa.Column("id", sa.String(length=8), nullable=False),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("mode", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column(
            "pipeline_template_id",
            sa.String(),
            sa.ForeignKey("pipeline_template.id"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # Tasks table
    op.create_table(
        "task",
        sa.Column("id", sa.String(length=8), nullable=False),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("purpose_id", sa.String(), sa.ForeignKey("purpose.id"), nullable=True),
        sa.Column(
            "pipeline_phase_id",
            sa.String(),
            sa.ForeignKey("pipeline_phase.id"),
            nullable=True,
        ),
        sa.Column("description", sa.String(length=2000), nullable=False),
        sa.Column("business_value", sa.Float(), nullable=False),
        sa.Column("tokens_plan", sa.Integer(), nullable=False),
        sa.Column("tokens_actual", sa.Integer(), nullable=False),
        sa.Column("purpose_relevance", sa.Float(), nullable=False),
        sa.Column("agent_role", sa.String(length=100), nullable=True),
        sa.Column("model_name", sa.String(length=255), nullable=True),
        sa.Column("prompt_template", sa.String(length=255), nullable=True),
        sa.Column("requires_approval", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("owner", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("retries", sa.Integer(), nullable=False),
        sa.Column("issues_found", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "task_dependency",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("from_id", sa.String(), sa.ForeignKey("task.id"), nullable=False),
        sa.Column("to_id", sa.String(), sa.ForeignKey("task.id"), nullable=False),
        sa.Column("dependency_type", sa.String(length=50), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    # Artifacts and feedback
    op.create_table(
        "artifact",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("task_id", sa.String(), sa.ForeignKey("task.id"), nullable=False),
        sa.Column("repo_path", sa.Text(), nullable=False),
        sa.Column("media_type", sa.String(length=100), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("released", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "feedback",
        sa.Column("id", sa.String(length=8), nullable=False),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("purpose_id", sa.String(), sa.ForeignKey("purpose.id"), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    # Chat messages and context
    op.create_table(
        "chatmessage",
        sa.Column("id", sa.String(length=8), nullable=False),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("purpose_id", sa.String(), sa.ForeignKey("purpose.id"), nullable=True),
        sa.Column("artifact_id", sa.String(), sa.ForeignKey("artifact.id"), nullable=True),
        sa.Column("task_id", sa.String(), sa.ForeignKey("task.id"), nullable=True),
        sa.Column(
            "role",
            sa.Enum("user", "assistant", "agent", name="chatrole"),
            nullable=False,
        ),
        sa.Column(
            "scope",
            sa.Enum("global", "artifact", "mixed", name="chatscope"),
            nullable=False,
        ),
        sa.Column(
            "intent",
            sa.Enum("question", "feedback", "note", "approval", name="chatintent"),
            nullable=False,
        ),
        sa.Column("content", sa.String(length=5000), nullable=False),
        sa.Column(
            "metadata",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "chatthreadcontext",
        sa.Column("purpose_id", sa.String(), sa.ForeignKey("purpose.id"), nullable=False),
        sa.Column("summary", sa.String(length=5000), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("purpose_id"),
    )
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
    # Tenant prompt assignment mapping
    op.create_table(
        "tenant_prompt_assignment",
        sa.Column("id", sa.String(length=8), nullable=False),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("phase_slug", sa.String(length=64), nullable=False),
        sa.Column("agent", sa.String(length=100), nullable=True),
        sa.Column(
            "prompt_template_id",
            sa.String(),
            sa.ForeignKey("prompt_template.id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    # Create indexes for frequently queried columns
    op.create_index(op.f("ix_pipeline_phase_slug"), "pipeline_phase", ["slug"], unique=False)
    op.create_index(
        op.f("ix_prompt_template_phase_slug"),
        "prompt_template",
        ["phase_slug"],
        unique=False,
    )


def downgrade() -> None:
    # Downgrade by dropping all created tables
    op.drop_index(op.f("ix_prompt_template_phase_slug"), table_name="prompt_template")
    op.drop_index(op.f("ix_pipeline_phase_slug"), table_name="pipeline_phase")
    op.drop_table("tenant_prompt_assignment")
    op.drop_table("chatmessageartifact")
    op.drop_table("chatthreadcontext")
    op.drop_table("chatmessage")
    op.drop_table("feedback")
    op.drop_table("artifact")
    op.drop_table("task_dependency")
    op.drop_table("task")
    op.drop_table("purpose")
    op.drop_table("pipeline_phase")
    op.drop_table("pipeline_template")
    op.drop_table("prompt_template")
    op.drop_table("tenant")
