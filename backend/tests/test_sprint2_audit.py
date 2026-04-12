"""Sprint 2 (Audit) integration tests: Approval & Feedback Re-Execution.

Tests cover:
- S2-#5:  WebSocket approval routes through centralized approve_artifact()
- S2-#4:  Feedback integration triggers redispatch_agent() for invalidated tasks
- S2-#13: Completed fix tasks auto-trigger re-review via dispatch_re_review()
"""

# Python 3.10 compatibility shim (project requires 3.11+ for StrEnum)
import enum
if not hasattr(enum, "StrEnum"):
    try:
        from strenum import StrEnum
        enum.StrEnum = StrEnum
    except ImportError:
        pass

import uuid
from datetime import datetime as dt
from unittest.mock import MagicMock, patch, call

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def test_engine():
    _engine = create_engine(
        "sqlite://",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Import all models to ensure they're registered in metadata
    import ai_org_backend.models  # noqa: F401
    import ai_org_backend.models.chat  # noqa: F401
    import ai_org_backend.models.code_review_finding  # noqa: F401

    SQLModel.metadata.create_all(_engine)
    return _engine


@pytest.fixture(autouse=True)
def patch_engine(test_engine, monkeypatch):
    """Patch the engine into every module that imports it at the top level."""
    import ai_org_backend.db as db_mod
    monkeypatch.setattr(db_mod, "engine", test_engine)

    # Also mock SessionLocal to use our test engine
    def _session_local():
        return Session(test_engine)
    monkeypatch.setattr(db_mod, "SessionLocal", _session_local)

    import ai_org_backend.services.approval as approval_mod
    monkeypatch.setattr(approval_mod, "engine", test_engine)

    import ai_org_backend.services.feedback_loop as fl_mod
    monkeypatch.setattr(fl_mod, "engine", test_engine)

    import ai_org_backend.services.review_gate as rg_mod
    monkeypatch.setattr(rg_mod, "engine", test_engine)

    import ai_org_backend.services.artifact_workflow as aw_mod
    monkeypatch.setattr(aw_mod, "engine", test_engine)


@pytest.fixture
def db_session(test_engine):
    with Session(test_engine) as session:
        yield session


@pytest.fixture
def tenant(db_session):
    from ai_org_backend.models import Tenant
    t = Tenant(
        id=f"t-s2-{uuid.uuid4().hex[:6]}",
        name="Test S2",
        email="s2@test.com",
        hashed_password="x",
    )
    db_session.add(t)
    db_session.commit()
    return t


@pytest.fixture
def purpose(db_session, tenant):
    from ai_org_backend.models import Purpose
    p = Purpose(
        id=f"p-s2-{uuid.uuid4().hex[:6]}",
        tenant_id=tenant.id,
        name="Test Purpose S2",
        mode="auto",
    )
    db_session.add(p)
    db_session.commit()
    return p


def _make_task(db_session, tenant, purpose, description, status="done", **kw):
    from ai_org_backend.models import Task
    task = Task(
        id=f"task-{uuid.uuid4().hex[:8]}",
        tenant_id=tenant.id,
        purpose_id=purpose.id,
        description=description,
        status=status,
        **kw,
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


def _make_artifact(db_session, task, *, size=100, released=False):
    from ai_org_backend.models.artifact import Artifact
    art = Artifact(
        id=f"art-{uuid.uuid4().hex[:8]}",
        task_id=task.id,
        repo_path=f"test/{uuid.uuid4().hex[:6]}.md",
        media_type="text/markdown",
        size=size,
        sha256="a" * 64,
        released=released,
    )
    db_session.add(art)
    db_session.commit()
    db_session.refresh(art)
    return art


def _make_dependency(db_session, from_task, to_task, dep_type="FINISH_START"):
    from ai_org_backend.models import TaskDependency
    dep = TaskDependency(
        from_id=from_task.id,
        to_id=to_task.id,
        dependency_type=dep_type,
    )
    db_session.add(dep)
    db_session.commit()
    return dep


# ──────────────────────────────────────────────────────────────────────
# S2-#5: WebSocket Approval via centralized service
# ──────────────────────────────────────────────────────────────────────


class TestWebSocketApprovalCentralized:
    """Fix #5: WebSocket approval path now delegates to approve_artifact()."""

    def test_ws_approval_calls_approve_artifact(self, db_session, tenant, purpose):
        """The WS approval block in chat.py imports and calls approve_artifact."""
        # Verify the import exists in the WS approval block
        import ast
        import inspect
        from ai_org_backend.api import chat as chat_mod

        source = inspect.getsource(chat_mod.websocket_chat)
        # The source should contain approve_artifact reference
        assert "approve_artifact" in source, (
            "WebSocket handler must delegate to approve_artifact()"
        )
        # Should NOT contain direct 'artifact.released = True' mutation
        # (the old pattern that bypassed the service)
        # Count occurrences: there should be zero direct assignment
        lines = source.splitlines()
        direct_mutations = [
            l for l in lines
            if "artifact.released = True" in l and "approve_artifact" not in l
        ]
        assert len(direct_mutations) == 0, (
            "WebSocket handler must NOT directly mutate artifact.released; "
            f"found: {direct_mutations}"
        )

    def test_approve_artifact_sets_released_and_done(self, db_session, tenant, purpose):
        """approve_artifact() correctly marks artifact as released and task as done."""
        from ai_org_backend.services.approval import approve_artifact

        task = _make_task(db_session, tenant, purpose, "Vision Document", status="todo",
                          notes="awaiting_approval")
        art = _make_artifact(db_session, task, released=False)

        with patch("ai_org_backend.services.approval.pool") as mock_pool:
            mock_pool.get.return_value = None
            result = approve_artifact(
                art.id,
                tenant_id=tenant.id,
                purpose_id=purpose.id,
                session=db_session,
            )

        assert result.artifact_id == art.id
        assert result.task_id == task.id
        assert not result.previously_released
        # Verify in DB
        db_session.refresh(art)
        db_session.refresh(task)
        assert art.released is True
        assert task.status == "done"
        assert "approved" in (task.notes or "")

    def test_approve_artifact_idempotent_on_already_released(self, db_session, tenant, purpose):
        """Approving an already-released artifact returns previously_released=True."""
        from ai_org_backend.services.approval import approve_artifact

        task = _make_task(db_session, tenant, purpose, "PRD", status="done",
                          notes="approved")
        art = _make_artifact(db_session, task, released=True)

        with patch("ai_org_backend.services.approval.pool") as mock_pool:
            mock_pool.get.return_value = None
            result = approve_artifact(art.id, session=db_session)

        assert result.previously_released is True

    def test_approve_artifact_not_found(self, db_session, tenant, purpose):
        """approve_artifact raises ArtifactNotFoundError for missing artifacts."""
        from ai_org_backend.services.approval import approve_artifact, ArtifactNotFoundError

        with patch("ai_org_backend.services.approval.pool") as mock_pool:
            mock_pool.get.return_value = None
            with pytest.raises(ArtifactNotFoundError):
                approve_artifact("nonexistent-art-id", session=db_session)


# ──────────────────────────────────────────────────────────────────────
# S2-#4: Feedback Re-Dispatch
# ──────────────────────────────────────────────────────────────────────


class TestFeedbackRedispatch:
    """Fix #4: After feedback integration, invalidated tasks are re-dispatched."""

    def test_integrate_prd_feedback_triggers_redispatch(self, db_session, tenant, purpose):
        """integrate_prd_feedback calls cascade_invalidation then redispatch_agent."""
        # Verify the source code of integrate_prd_feedback contains redispatch_agent
        import inspect
        from ai_org_backend.services import artifact_workflow as aw_mod
        source = inspect.getsource(aw_mod.integrate_prd_feedback)
        assert "redispatch_agent" in source, (
            "integrate_prd_feedback must call redispatch_agent for invalidated tasks"
        )
        assert "cascade_invalidation" in source, (
            "integrate_prd_feedback must call cascade_invalidation"
        )

    def test_cascade_then_redispatch_end_to_end(self, db_session, tenant, purpose):
        """After cascade_invalidation, downstream tasks are invalidated and can be redispatched."""
        from ai_org_backend.services.feedback_loop import cascade_invalidation

        prd_task = _make_task(db_session, tenant, purpose,
                              "PRD Phase", status="done")
        arch_task = _make_task(db_session, tenant, purpose,
                               "Arch Phase", status="done",
                               owner="ARCHITECT", agent_role="architect")
        arch_art = _make_artifact(db_session, arch_task, released=True)
        _make_dependency(db_session, prd_task, arch_task)

        result = cascade_invalidation(prd_task.id, purpose_id=purpose.id)
        assert arch_task.id in result.invalidated_task_ids
        db_session.refresh(arch_task)
        assert arch_task.status == "todo"

    def test_ws_feedback_path_has_invalidation(self):
        """WebSocket feedback path includes cascade_invalidation + redispatch calls."""
        import inspect
        from ai_org_backend.api import chat as chat_mod

        source = inspect.getsource(chat_mod.websocket_chat)
        assert "cascade_invalidation" in source, (
            "WebSocket feedback path must call cascade_invalidation"
        )
        assert "redispatch_agent" in source, (
            "WebSocket feedback path must call redispatch_agent"
        )

    def test_redispatch_agent_sends_celery_task(self, db_session, tenant, purpose):
        """redispatch_agent() sends a Celery task and updates task status to DOING."""
        task = _make_task(db_session, tenant, purpose,
                          "Architecture Blueprint", status="todo",
                          owner="ARCHITECT", agent_role="architect")

        with patch("ai_org_backend.tasks.celery_app.celery") as mock_celery:
            mock_celery.send_task = MagicMock()

            from ai_org_backend.services.feedback_loop import redispatch_agent
            result = redispatch_agent(task.id, tenant_id=tenant.id)

        assert result is True
        mock_celery.send_task.assert_called_once()
        call_args = mock_celery.send_task.call_args
        assert "architect" in call_args[0][0]  # task name contains role

    def test_redispatch_agent_missing_task(self, db_session):
        """redispatch_agent returns False for nonexistent task."""
        with patch("ai_org_backend.tasks.celery_app.celery") as mock_celery:
            mock_celery.send_task = MagicMock()
            from ai_org_backend.services.feedback_loop import redispatch_agent
            result = redispatch_agent("nonexistent-task-id")
        assert result is False

    def test_cascade_invalidation_resets_downstream(self, db_session, tenant, purpose):
        """cascade_invalidation resets downstream tasks to todo and un-releases artifacts."""
        from ai_org_backend.services.feedback_loop import cascade_invalidation

        task_a = _make_task(db_session, tenant, purpose, "Phase A", status="done")
        task_b = _make_task(db_session, tenant, purpose, "Phase B", status="done")
        art_b = _make_artifact(db_session, task_b, released=True)
        _make_dependency(db_session, task_a, task_b)

        result = cascade_invalidation(task_a.id, purpose_id=purpose.id)

        assert task_b.id in result.invalidated_task_ids
        assert art_b.id in result.invalidated_artifact_ids
        db_session.refresh(task_b)
        db_session.refresh(art_b)
        assert task_b.status == "todo"
        assert art_b.released is False


# ──────────────────────────────────────────────────────────────────────
# S2-#13: Auto Re-Review on Fix Task Completion
# ──────────────────────────────────────────────────────────────────────


class TestAutoReReview:
    """Fix #13: Completed fix tasks auto-trigger dispatch_re_review()."""

    def test_celery_task_success_handler_exists(self):
        """celery_app.py has a task_success signal handler for re-review."""
        import inspect
        from ai_org_backend.tasks import celery_app as ca_mod

        assert hasattr(ca_mod, "check_fix_task_re_review"), (
            "celery_app.py must define check_fix_task_re_review handler"
        )

    def test_check_fix_tasks_complete_all_done(self, db_session, tenant, purpose):
        """check_fix_tasks_complete returns True when all fix tasks are done."""
        from ai_org_backend.services.review_gate import check_fix_tasks_complete

        review_task = _make_task(db_session, tenant, purpose,
                                  "Architecture & Domain Review", status="doing")
        fix_task = _make_task(db_session, tenant, purpose,
                               "Review Fix: auth.py", status="done")
        _make_dependency(db_session, fix_task, review_task, dep_type="blocks")

        assert check_fix_tasks_complete(review_task.id) is True

    def test_check_fix_tasks_complete_some_pending(self, db_session, tenant, purpose):
        """check_fix_tasks_complete returns False when some fix tasks are not done."""
        from ai_org_backend.services.review_gate import check_fix_tasks_complete

        review_task = _make_task(db_session, tenant, purpose,
                                  "Code Review", status="doing")
        fix1 = _make_task(db_session, tenant, purpose,
                           "Review Fix: api.py", status="done")
        fix2 = _make_task(db_session, tenant, purpose,
                           "Review Fix: db.py", status="todo")
        _make_dependency(db_session, fix1, review_task, dep_type="blocks")
        _make_dependency(db_session, fix2, review_task, dep_type="blocks")

        assert check_fix_tasks_complete(review_task.id) is False

    def test_dispatch_re_review_increments_round(self, db_session, tenant, purpose):
        """dispatch_re_review increments review_rounds and dispatches Celery task."""
        from ai_org_backend.services.review_gate import dispatch_re_review

        review_task = _make_task(db_session, tenant, purpose,
                                  "Architecture & Domain Review", status="doing")
        # Ensure review_rounds is 0 initially
        review_task.review_rounds = 0
        db_session.add(review_task)
        db_session.commit()

        with patch("ai_org_backend.tasks.celery_app.celery") as mock_celery:
            mock_celery.send_task = MagicMock()
            result = dispatch_re_review(review_task.id, tenant.id)

        assert result is True
        db_session.refresh(review_task)
        assert review_task.review_rounds == 1

    def test_dispatch_re_review_escalates_after_max_rounds(self, db_session, tenant, purpose):
        """dispatch_re_review escalates to manual review after MAX_REVIEW_ROUNDS."""
        from ai_org_backend.services.review_gate import dispatch_re_review, MAX_REVIEW_ROUNDS

        review_task = _make_task(db_session, tenant, purpose,
                                  "Code Review Gate", status="doing")
        review_task.review_rounds = MAX_REVIEW_ROUNDS - 1  # next increment hits max
        db_session.add(review_task)
        db_session.commit()

        with patch("ai_org_backend.tasks.celery_app.celery") as mock_celery:
            mock_celery.send_task = MagicMock()
            result = dispatch_re_review(review_task.id, tenant.id)

        assert result is False  # Escalated, not dispatched
        db_session.refresh(review_task)
        assert review_task.code_review_status == "requires_manual_review"
        assert "escalated" in (review_task.notes or "")

    def test_task_success_handler_triggers_re_review(self, db_session, tenant, purpose):
        """End-to-end: task_success handler detects fix task and triggers re-review."""
        from ai_org_backend.tasks.celery_app import check_fix_task_re_review

        review_task = _make_task(db_session, tenant, purpose,
                                  "Architecture & Domain Review", status="doing")
        review_task.review_rounds = 0
        db_session.add(review_task)
        db_session.commit()

        fix_task = _make_task(db_session, tenant, purpose,
                               "Review Fix: handler.py", status="done")
        _make_dependency(db_session, fix_task, review_task, dep_type="blocks")

        with patch("ai_org_backend.tasks.celery_app.celery") as mock_celery:
            mock_celery.send_task = MagicMock()
            # Simulate task_success signal
            check_fix_task_re_review(
                sender=None,
                result=None,
                args=[tenant.id, fix_task.id],
            )

        # Re-review should have been dispatched
        mock_celery.send_task.assert_called_once()
        call_args = mock_celery.send_task.call_args
        assert "code_review" in call_args[0][0]

    def test_task_success_handler_ignores_non_fix_tasks(self, db_session, tenant, purpose):
        """task_success handler ignores tasks that are not review fix tasks."""
        from ai_org_backend.tasks.celery_app import check_fix_task_re_review

        regular_task = _make_task(db_session, tenant, purpose,
                                   "Architecture Blueprint", status="done")

        with patch("ai_org_backend.tasks.celery_app.celery") as mock_celery:
            mock_celery.send_task = MagicMock()
            check_fix_task_re_review(
                sender=None,
                result=None,
                args=[tenant.id, regular_task.id],
            )

        # Should NOT dispatch re-review for a regular task
        mock_celery.send_task.assert_not_called()
