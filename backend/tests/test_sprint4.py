"""Sprint 4 integration tests: Approval + Feedback.

Tests cover:
- S4-01: Central approve_artifact() service
- S4-03: Idempotency tokens
- S4-04: requires_approval enforcement
- S4-06: Position-based dispatch ordering
- S4-07: Transitive predecessor check
- S4-08: Downstream invalidation after feedback
- S4-09: Agent re-dispatch
- S4-10: Cascading invalidation (artifact chain)
- S4-11: Feedback as context in agent prompt
"""

import uuid
from datetime import datetime as dt
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture(scope="module")
def test_engine():
    engine = create_engine(
        "sqlite://",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture(autouse=True)
def patch_engine(test_engine, monkeypatch):
    import ai_org_backend.db as db_mod
    monkeypatch.setattr(db_mod, "engine", test_engine)


@pytest.fixture
def db_session(test_engine):
    with Session(test_engine) as session:
        yield session


@pytest.fixture
def tenant(db_session):
    from ai_org_backend.models import Tenant
    t = Tenant(id="test-s4", name="Test S4", email="t@t.com", hashed_password="x")
    db_session.add(t)
    db_session.commit()
    return t


@pytest.fixture
def purpose(db_session, tenant):
    from ai_org_backend.models import Purpose
    p = Purpose(
        id=str(uuid.uuid4())[:8],
        tenant_id=tenant.id,
        name="Test Purpose S4",
        mode="manual",
    )
    db_session.add(p)
    db_session.commit()
    return p


@pytest.fixture
def task_with_artifact(db_session, tenant, purpose):
    """Create a task with a released artifact."""
    from ai_org_backend.models import Task
    from ai_org_backend.models.artifact import Artifact

    task = Task(
        id=str(uuid.uuid4())[:8],
        tenant_id=tenant.id,
        purpose_id=purpose.id,
        description="Vision Document",
        status="done",
        notes="awaiting_approval",
    )
    db_session.add(task)
    db_session.flush()

    artifact = Artifact(
        id=str(uuid.uuid4())[:8],
        task_id=task.id,
        repo_path="test/vision.md",
        media_type="text/markdown",
        size=100,
        sha256="a" * 64,
        released=False,
    )
    db_session.add(artifact)
    db_session.commit()
    return task, artifact


# ──────────────────────────────────────────────────────────────────────
# S4-01: Central approve_artifact() service
# ──────────────────────────────────────────────────────────────────────


class TestApprovalService:
    def test_approve_sets_released(self, db_session, task_with_artifact):
        from ai_org_backend.services.approval import approve_artifact
        task, artifact = task_with_artifact

        result = approve_artifact(
            artifact.id,
            session=db_session,
            clear_pause=False,
        )
        assert result.artifact_id == artifact.id
        assert result.task_id == task.id
        assert result.phase_hint == "vision"
        assert not result.previously_released

        # Verify in DB
        db_session.refresh(artifact)
        assert artifact.released is True

    def test_approve_already_released_returns_flag(self, db_session, task_with_artifact):
        from ai_org_backend.services.approval import approve_artifact
        task, artifact = task_with_artifact

        # First approval
        approve_artifact(artifact.id, session=db_session, clear_pause=False)

        # Second approval
        result = approve_artifact(artifact.id, session=db_session, clear_pause=False)
        assert result.previously_released is True

    def test_approve_nonexistent_raises(self, db_session):
        from ai_org_backend.services.approval import (
            ArtifactNotFoundError,
            approve_artifact,
        )
        with pytest.raises(ArtifactNotFoundError):
            approve_artifact("nonexistent-id", session=db_session)

    def test_approve_updates_task_notes(self, db_session, tenant, purpose):
        from ai_org_backend.models import Task
        from ai_org_backend.models.artifact import Artifact
        from ai_org_backend.services.approval import approve_artifact

        task = Task(
            id=str(uuid.uuid4())[:8],
            tenant_id=tenant.id,
            purpose_id=purpose.id,
            description="Product Requirements Document",
            status="doing",
            notes="awaiting_approval",
        )
        db_session.add(task)
        db_session.flush()
        art = Artifact(
            id=str(uuid.uuid4())[:8],
            task_id=task.id,
            repo_path="test/prd.md",
            media_type="text/markdown",
            size=200,
            sha256="b" * 64,
            released=False,
        )
        db_session.add(art)
        db_session.commit()

        approve_artifact(art.id, session=db_session, clear_pause=False)

        db_session.refresh(task)
        assert "approved" in task.notes
        assert task.status == "done"
        assert "awaiting_approval" not in task.notes

    def test_phase_hint_detection(self, db_session, tenant, purpose):
        from ai_org_backend.models import Task
        from ai_org_backend.models.artifact import Artifact
        from ai_org_backend.services.approval import approve_artifact

        cases = [
            ("Architecture Blueprint", "blueprints/bp.md", "architecture"),
            ("Architecture & Domain Review", "reviews/rev.md", "review"),
        ]
        for desc, path, expected_hint in cases:
            task = Task(
                id=str(uuid.uuid4())[:8],
                tenant_id=tenant.id,
                purpose_id=purpose.id,
                description=desc,
                status="doing",
            )
            db_session.add(task)
            db_session.flush()
            art = Artifact(
                id=str(uuid.uuid4())[:8],
                task_id=task.id,
                repo_path=path,
                media_type="text/markdown",
                size=100,
                sha256=str(uuid.uuid4()).replace("-", "") + "0" * 32,
                released=False,
            )
            db_session.add(art)
            db_session.commit()
            result = approve_artifact(art.id, session=db_session, clear_pause=False)
            assert result.phase_hint == expected_hint, f"Expected {expected_hint} for {desc}"


# ──────────────────────────────────────────────────────────────────────
# S4-03: Idempotency token
# ──────────────────────────────────────────────────────────────────────


class TestIdempotencyToken:
    def test_idempotency_token_prevents_double_approval(self, db_session, tenant, purpose):
        from ai_org_backend.models import Task
        from ai_org_backend.models.artifact import Artifact
        from ai_org_backend.services.approval import approve_artifact

        task = Task(
            id=str(uuid.uuid4())[:8],
            tenant_id=tenant.id,
            purpose_id=purpose.id,
            description="Test Task Idempotent",
            status="doing",
        )
        db_session.add(task)
        db_session.flush()
        art = Artifact(
            id=str(uuid.uuid4())[:8],
            task_id=task.id,
            repo_path="test/idem.md",
            media_type="text/markdown",
            size=100,
            sha256="c" * 64,
            released=False,
        )
        db_session.add(art)
        db_session.commit()

        token = f"idem-{uuid.uuid4()}"

        # First call
        with patch("ai_org_backend.services.approval.pool") as mock_pool:
            mock_pool.get.return_value = None
            result1 = approve_artifact(
                art.id,
                idempotency_token=token,
                session=db_session,
                clear_pause=False,
            )
            assert not result1.idempotent_hit

        # Second call with same token – mock Redis returns cached value
        with patch("ai_org_backend.services.approval.pool") as mock_pool:
            mock_pool.get.return_value = art.id.encode()
            result2 = approve_artifact(
                art.id,
                idempotency_token=token,
                session=db_session,
                clear_pause=False,
            )
            assert result2.idempotent_hit is True


# ──────────────────────────────────────────────────────────────────────
# S4-04 / S4-07: Transitive predecessor + requires_approval
# ──────────────────────────────────────────────────────────────────────


class TestTransitivePredecessor:
    def test_ready_blocks_on_undone_transitive(self, db_session, tenant, purpose):
        from ai_org_backend.models import Task, TaskDependency
        from ai_org_backend.orchestrator.scheduler import _ready_for_execution

        # A → B → C (C should be blocked if A is not done)
        a = Task(
            id="t-a", tenant_id=tenant.id, purpose_id=purpose.id,
            description="Task A", status="todo",
        )
        b = Task(
            id="t-b", tenant_id=tenant.id, purpose_id=purpose.id,
            description="Task B", status="done",
        )
        c = Task(
            id="t-c", tenant_id=tenant.id, purpose_id=purpose.id,
            description="Task C", status="todo",
        )
        db_session.add_all([a, b, c])
        db_session.flush()

        db_session.add(TaskDependency(from_id="t-a", to_id="t-b", dependency_type="blocks"))
        db_session.add(TaskDependency(from_id="t-b", to_id="t-c", dependency_type="blocks"))
        db_session.commit()

        # C should not be ready because A is not done
        assert _ready_for_execution(c, db_session) is False

        # Mark A as done
        a.status = "done"
        db_session.add(a)
        db_session.commit()

        # Now C should be ready
        assert _ready_for_execution(c, db_session) is True

    def test_requires_approval_blocks_downstream(self, db_session, tenant, purpose):
        from ai_org_backend.models import Task, TaskDependency
        from ai_org_backend.models.artifact import Artifact
        from ai_org_backend.orchestrator.scheduler import _ready_for_execution

        parent = Task(
            id="t-parent", tenant_id=tenant.id, purpose_id=purpose.id,
            description="Parent Task", status="done", requires_approval=True,
        )
        child = Task(
            id="t-child", tenant_id=tenant.id, purpose_id=purpose.id,
            description="Child Task", status="todo",
        )
        db_session.add_all([parent, child])
        db_session.flush()
        db_session.add(TaskDependency(from_id="t-parent", to_id="t-child", dependency_type="blocks"))

        # Parent artifact not released
        art = Artifact(
            id="art-parent",
            task_id="t-parent",
            repo_path="test/parent.md",
            media_type="text/markdown",
            size=100,
            sha256="d" * 64,
            released=False,
        )
        db_session.add(art)
        db_session.commit()

        # Child should be blocked because parent requires approval and artifact not released
        assert _ready_for_execution(child, db_session) is False

        # Release the artifact
        art.released = True
        db_session.add(art)
        db_session.commit()

        # Now child should be ready
        assert _ready_for_execution(child, db_session) is True


# ──────────────────────────────────────────────────────────────────────
# S4-06: Position-based dispatch ordering
# ──────────────────────────────────────────────────────────────────────


class TestPositionSorting:
    def test_get_task_position_default(self, db_session, tenant, purpose):
        from ai_org_backend.models import Task
        from ai_org_backend.orchestrator.scheduler import _get_task_position

        task = Task(
            id="t-nopos", tenant_id=tenant.id, purpose_id=purpose.id,
            description="Random Task", status="todo",
        )
        db_session.add(task)
        db_session.commit()

        # No pipeline phase → default position 9999
        pos = _get_task_position(db_session, task)
        assert pos == 9999

    def test_get_task_position_from_phase(self, db_session, tenant, purpose):
        from ai_org_backend.models import Task
        from ai_org_backend.models.pipeline import PipelinePhase, PipelineTemplate
        from ai_org_backend.orchestrator.scheduler import _get_task_position

        tmpl = PipelineTemplate(id="tmpl-s4", name="Test Template", tenant_id=tenant.id)
        db_session.add(tmpl)
        db_session.flush()

        phase = PipelinePhase(
            id="phase-s4", pipeline_template_id=tmpl.id,
            name="Dev Phase", slug="dev", position=5,
        )
        db_session.add(phase)
        db_session.flush()

        task = Task(
            id="t-withpos", tenant_id=tenant.id, purpose_id=purpose.id,
            description="Dev Task", status="todo", pipeline_phase_id="phase-s4",
        )
        db_session.add(task)
        db_session.commit()

        pos = _get_task_position(db_session, task)
        assert pos == 5


# ──────────────────────────────────────────────────────────────────────
# S4-08: Downstream invalidation
# ──────────────────────────────────────────────────────────────────────


class TestDownstreamInvalidation:
    def test_invalidates_downstream_artifacts(self, db_session, tenant, purpose):
        from ai_org_backend.models import Task, TaskDependency
        from ai_org_backend.models.artifact import Artifact
        from ai_org_backend.services.feedback_loop import invalidate_downstream

        prd_task = Task(
            id="t-prd-inv", tenant_id=tenant.id, purpose_id=purpose.id,
            description="PRD", status="done",
        )
        arch_task = Task(
            id="t-arch-inv", tenant_id=tenant.id, purpose_id=purpose.id,
            description="Architecture", status="done",
        )
        db_session.add_all([prd_task, arch_task])
        db_session.flush()
        db_session.add(TaskDependency(from_id="t-prd-inv", to_id="t-arch-inv", dependency_type="blocks"))

        arch_art = Artifact(
            id="art-arch-inv",
            task_id="t-arch-inv",
            repo_path="test/arch.md",
            media_type="text/markdown",
            size=200,
            sha256="e" * 64,
            released=True,
        )
        db_session.add(arch_art)
        db_session.commit()

        result = invalidate_downstream("t-prd-inv", purpose_id=purpose.id, session=db_session)

        assert "art-arch-inv" in result.invalidated_artifact_ids
        assert "t-arch-inv" in result.invalidated_task_ids

        db_session.refresh(arch_art)
        assert arch_art.released is False

        db_session.refresh(arch_task)
        assert arch_task.status == "todo"

    def test_no_downstream_no_invalidation(self, db_session, tenant, purpose):
        from ai_org_backend.models import Task
        from ai_org_backend.services.feedback_loop import invalidate_downstream

        lone_task = Task(
            id="t-lone", tenant_id=tenant.id, purpose_id=purpose.id,
            description="Lone Task", status="done",
        )
        db_session.add(lone_task)
        db_session.commit()

        result = invalidate_downstream("t-lone", purpose_id=purpose.id, session=db_session)
        assert result.invalidated_artifact_ids == []
        assert result.invalidated_task_ids == []


# ──────────────────────────────────────────────────────────────────────
# S4-10: Cascading invalidation
# ──────────────────────────────────────────────────────────────────────


class TestCascadingInvalidation:
    def test_cascades_through_chain(self, db_session, tenant, purpose):
        from ai_org_backend.models import Task, TaskDependency
        from ai_org_backend.models.artifact import Artifact
        from ai_org_backend.services.feedback_loop import cascade_invalidation

        # PRD → Architecture → Review (cascade should reach Review)
        t1 = Task(id="t-c1", tenant_id=tenant.id, purpose_id=purpose.id, description="PRD C", status="done")
        t2 = Task(id="t-c2", tenant_id=tenant.id, purpose_id=purpose.id, description="Arch C", status="done")
        t3 = Task(id="t-c3", tenant_id=tenant.id, purpose_id=purpose.id, description="Review C", status="done")
        db_session.add_all([t1, t2, t3])
        db_session.flush()
        db_session.add(TaskDependency(from_id="t-c1", to_id="t-c2", dependency_type="blocks"))
        db_session.add(TaskDependency(from_id="t-c2", to_id="t-c3", dependency_type="blocks"))

        art2 = Artifact(
            id="art-c2", task_id="t-c2", repo_path="test/c2.md",
            media_type="text/markdown", size=100, sha256="f" * 64, released=True,
        )
        art3 = Artifact(
            id="art-c3", task_id="t-c3", repo_path="test/c3.md",
            media_type="text/markdown", size=100, sha256="0" * 64, released=True,
        )
        db_session.add_all([art2, art3])
        db_session.commit()

        result = cascade_invalidation("t-c1", purpose_id=purpose.id)

        # Both downstream artifacts should be invalidated
        assert "art-c2" in result.invalidated_artifact_ids
        assert "art-c3" in result.invalidated_artifact_ids
        assert "t-c2" in result.invalidated_task_ids
        assert "t-c3" in result.invalidated_task_ids


# ──────────────────────────────────────────────────────────────────────
# S4-09: Agent re-dispatch
# ──────────────────────────────────────────────────────────────────────


class TestAgentRedispatch:
    def test_redispatch_sets_doing(self, db_session, tenant, purpose):
        from ai_org_backend.models import Task
        from ai_org_backend.services.feedback_loop import redispatch_agent

        task = Task(
            id="t-redisp", tenant_id=tenant.id, purpose_id=purpose.id,
            description="Redispatch Test", status="todo",
            agent_role="dev",
        )
        db_session.add(task)
        db_session.commit()

        with patch("ai_org_backend.services.feedback_loop.celery") as mock_celery:
            result = redispatch_agent("t-redisp")
            assert result is True
            mock_celery.send_task.assert_called_once()

    def test_redispatch_missing_task(self):
        from ai_org_backend.services.feedback_loop import redispatch_agent
        result = redispatch_agent("nonexistent-task-id")
        assert result is False


# ──────────────────────────────────────────────────────────────────────
# S4-11: Feedback context loading
# ──────────────────────────────────────────────────────────────────────


class TestFeedbackContext:
    def test_empty_feedback_returns_empty_string(self, db_session, tenant, purpose):
        from ai_org_backend.models import Task
        from ai_org_backend.services.feedback_loop import load_feedback_context

        task = Task(
            id="t-fbctx", tenant_id=tenant.id, purpose_id=purpose.id,
            description="Feedback Context Test", status="done",
        )
        db_session.add(task)
        db_session.commit()

        ctx = load_feedback_context("t-fbctx")
        assert ctx == ""

    def test_feedback_with_messages(self, db_session, tenant, purpose):
        from ai_org_backend.models import Task
        from ai_org_backend.models.artifact import Artifact
        from ai_org_backend.models.chat import ChatIntent, ChatMessage, ChatMessageArtifact, ChatRole, ChatScope
        from ai_org_backend.services.feedback_loop import load_feedback_context

        task = Task(
            id="t-fbmsg", tenant_id=tenant.id, purpose_id=purpose.id,
            description="Feedback Msg Test", status="done",
        )
        db_session.add(task)
        db_session.flush()

        art = Artifact(
            id="art-fbmsg", task_id="t-fbmsg", repo_path="test/fb.md",
            media_type="text/markdown", size=100, sha256="1" * 64, released=True,
        )
        db_session.add(art)
        db_session.flush()

        msg = ChatMessage(
            tenant_id=tenant.id,
            purpose_id=purpose.id,
            task_id="t-fbmsg",
            role=ChatRole.USER,
            content="Please add more detail to the security section",
            intent=ChatIntent.FEEDBACK,
            scope=ChatScope.ARTIFACT,
        )
        db_session.add(msg)
        db_session.flush()

        link = ChatMessageArtifact(chat_message_id=msg.id, artifact_id=art.id)
        db_session.add(link)
        db_session.commit()

        ctx = load_feedback_context("t-fbmsg")
        assert "Previous Feedback" in ctx
        assert "security section" in ctx
