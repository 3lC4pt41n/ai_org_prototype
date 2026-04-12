"""Sprint 1 (Audit) integration tests: Phase-Gate Artifact Validation.

Tests cover:
- S1-#1:  Phase gate blocks advancement when artifact is missing or empty
- S1-#2:  requires_approval enforcement (dead-code elimination)
- S1-#9:  ArtifactNotFoundError in artifact_resolver (explicit failure)
- S1-#12: Auto-mode approval gap closed in review_hook
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
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


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
    """Patch the engine into every module that imports it at the top level."""
    import ai_org_backend.db as db_mod

    monkeypatch.setattr(db_mod, "engine", test_engine)

    # Also patch modules that cache `engine` at import time
    import ai_org_backend.services.artifact_resolver as ar_mod
    import ai_org_backend.orchestrator.scheduler as sched_mod

    monkeypatch.setattr(ar_mod, "engine", test_engine)
    monkeypatch.setattr(sched_mod, "engine", test_engine)


@pytest.fixture
def db_session(test_engine):
    with Session(test_engine) as session:
        yield session


@pytest.fixture
def tenant(db_session):
    from ai_org_backend.models import Tenant

    t = Tenant(
        id=f"t-s1-{uuid.uuid4().hex[:6]}",
        name="Test S1",
        email="s1@test.com",
        hashed_password="x",
    )
    db_session.add(t)
    db_session.commit()
    return t


@pytest.fixture
def purpose_auto(db_session, tenant):
    from ai_org_backend.models import Purpose

    p = Purpose(
        id=f"p-auto-{uuid.uuid4().hex[:6]}",
        tenant_id=tenant.id,
        name="Test Purpose Auto",
        mode="auto",
    )
    db_session.add(p)
    db_session.commit()
    return p


@pytest.fixture
def purpose_manual(db_session, tenant):
    from ai_org_backend.models import Purpose

    p = Purpose(
        id=f"p-man-{uuid.uuid4().hex[:6]}",
        tenant_id=tenant.id,
        name="Test Purpose Manual",
        mode="manual",
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


# ──────────────────────────────────────────────────────────────────────
# S1-#1: Phase Gate blocks when artifact is missing or zero-size
# ──────────────────────────────────────────────────────────────────────


class TestPhaseGateArtifactValidation:
    """Fix #1: The orchestrator must NOT advance phases when the artifact
    for the previous phase is missing or empty, even in auto mode."""

    @patch("ai_org_backend.orchestrator.scheduler.celery")
    @patch("ai_org_backend.orchestrator.scheduler.pool")
    def test_auto_mode_blocks_prd_when_vision_artifact_missing(
        self, mock_pool, mock_celery, db_session, tenant, purpose_auto
    ):
        """Auto mode: Vision task DONE but NO artifact → PRD should NOT be created."""
        vision_task = _make_task(
            db_session, tenant, purpose_auto, "Vision Document", status="done"
        )
        # No artifact created!

        from ai_org_backend.orchestrator.scheduler import _generate_plan_for_purpose

        _generate_plan_for_purpose(purpose_auto.id)

        # Verify no PRD task was created
        from ai_org_backend.models import Task
        from sqlmodel import func, select

        prd = db_session.exec(
            select(Task).where(
                Task.purpose_id == purpose_auto.id,
                func.lower(Task.description) == "product requirements document",
            )
        ).first()
        assert prd is None, "PRD task should NOT be created when vision artifact is missing"

    @patch("ai_org_backend.orchestrator.scheduler.celery")
    @patch("ai_org_backend.orchestrator.scheduler.pool")
    def test_auto_mode_blocks_prd_when_vision_artifact_empty(
        self, mock_pool, mock_celery, db_session, tenant, purpose_auto
    ):
        """Auto mode: Vision task DONE with zero-size artifact → PRD should NOT be created."""
        vision_task = _make_task(
            db_session, tenant, purpose_auto, "Vision Document", status="done"
        )
        _make_artifact(db_session, vision_task, size=0)

        from ai_org_backend.orchestrator.scheduler import _generate_plan_for_purpose

        _generate_plan_for_purpose(purpose_auto.id)

        from ai_org_backend.models import Task
        from sqlmodel import func, select

        prd = db_session.exec(
            select(Task).where(
                Task.purpose_id == purpose_auto.id,
                func.lower(Task.description) == "product requirements document",
            )
        ).first()
        assert prd is None, "PRD task should NOT be created when vision artifact has size=0"

    @patch("ai_org_backend.orchestrator.scheduler.celery")
    @patch("ai_org_backend.orchestrator.scheduler.pool")
    def test_auto_mode_advances_prd_when_vision_artifact_exists(
        self, mock_pool, mock_celery, db_session, tenant, purpose_auto
    ):
        """Auto mode: Vision task DONE with valid artifact → PRD should be created."""
        vision_task = _make_task(
            db_session, tenant, purpose_auto, "Vision Document", status="done"
        )
        _make_artifact(db_session, vision_task, size=500)

        from ai_org_backend.orchestrator.scheduler import _generate_plan_for_purpose

        _generate_plan_for_purpose(purpose_auto.id)

        from ai_org_backend.models import Task
        from sqlmodel import func, select

        prd = db_session.exec(
            select(Task).where(
                Task.purpose_id == purpose_auto.id,
                func.lower(Task.description) == "product requirements document",
            )
        ).first()
        assert prd is not None, "PRD task should be created when vision artifact is valid"

    @patch("ai_org_backend.orchestrator.scheduler.celery")
    @patch("ai_org_backend.orchestrator.scheduler.pool")
    def test_prd_gate_blocks_architecture_when_artifact_empty(
        self, mock_pool, mock_celery, db_session, tenant, purpose_auto
    ):
        """PRD task DONE with zero-size artifact → architecture should NOT start."""
        _make_task(db_session, tenant, purpose_auto, "Vision Document", status="done")
        po_task = _make_task(
            db_session,
            tenant,
            purpose_auto,
            "Product Requirements Document",
            status="done",
        )
        _make_artifact(db_session, po_task, size=0)

        from ai_org_backend.orchestrator.scheduler import _generate_plan_for_purpose

        # This should not call run_architect because prd_ready_for_architecture is False
        with patch(
            "ai_org_backend.orchestrator.scheduler.run_architect"
        ) as mock_arch:
            _generate_plan_for_purpose(purpose_auto.id)
            mock_arch.assert_not_called()


# ──────────────────────────────────────────────────────────────────────
# S1-#2: requires_approval enforcement
# ──────────────────────────────────────────────────────────────────────


class TestRequiresApprovalEnforcement:
    """Fix #2: A task with requires_approval=True must have a released
    artifact before _ready_for_execution returns True."""

    def test_requires_approval_blocks_without_released_artifact(
        self, db_session, tenant, purpose_manual
    ):
        from ai_org_backend.orchestrator.scheduler import _ready_for_execution

        task = _make_task(
            db_session,
            tenant,
            purpose_manual,
            "Architecture & Domain Review",
            status="done",
            requires_approval=True,
        )
        # Artifact exists but NOT released
        _make_artifact(db_session, task, size=200, released=False)

        result = _ready_for_execution(task, db_session)
        assert result is False, (
            "Task with requires_approval=True and unreleased artifact "
            "should NOT be ready"
        )

    def test_requires_approval_allows_with_released_artifact(
        self, db_session, tenant, purpose_manual
    ):
        from ai_org_backend.orchestrator.scheduler import _ready_for_execution

        task = _make_task(
            db_session,
            tenant,
            purpose_manual,
            "Architecture Review OK",
            status="done",
            requires_approval=True,
        )
        _make_artifact(db_session, task, size=200, released=True)

        result = _ready_for_execution(task, db_session)
        assert result is True, (
            "Task with requires_approval=True and released artifact "
            "should be ready"
        )

    def test_requires_approval_blocks_without_any_artifact(
        self, db_session, tenant, purpose_manual
    ):
        from ai_org_backend.orchestrator.scheduler import _ready_for_execution

        task = _make_task(
            db_session,
            tenant,
            purpose_manual,
            "Review No Artifact",
            status="done",
            requires_approval=True,
        )
        # No artifact at all

        result = _ready_for_execution(task, db_session)
        assert result is False, (
            "Task with requires_approval=True and no artifact should NOT be ready"
        )

    def test_no_requires_approval_allows_without_artifact(
        self, db_session, tenant, purpose_manual
    ):
        from ai_org_backend.orchestrator.scheduler import _ready_for_execution

        task = _make_task(
            db_session,
            tenant,
            purpose_manual,
            "Simple Task",
            status="done",
            requires_approval=False,
        )

        result = _ready_for_execution(task, db_session)
        assert result is True, (
            "Task without requires_approval should be ready regardless of artifacts"
        )


# ──────────────────────────────────────────────────────────────────────
# S1-#9: ArtifactNotFoundError in artifact_resolver
# ──────────────────────────────────────────────────────────────────────


class TestArtifactNotFoundError:
    """Fix #9: load_by_phase with require_artifact=True must raise
    ArtifactNotFoundError instead of returning None."""

    def test_load_by_phase_raises_when_task_missing(self, db_session, tenant, purpose_auto):
        from ai_org_backend.services.artifact_resolver import (
            ArtifactNotFoundError,
            load_by_phase,
        )

        with pytest.raises(ArtifactNotFoundError, match="task not found"):
            load_by_phase(
                purpose_auto.id,
                "nonexistent phase",
                require_artifact=True,
            )

    def test_load_by_phase_raises_when_artifact_missing(
        self, db_session, tenant, purpose_auto
    ):
        from ai_org_backend.services.artifact_resolver import (
            ArtifactNotFoundError,
            load_by_phase,
        )

        # Task exists but no artifact
        _make_task(
            db_session, tenant, purpose_auto, "Orphaned Task", status="done"
        )

        with pytest.raises(ArtifactNotFoundError, match="no artifact on task"):
            load_by_phase(
                purpose_auto.id,
                "orphaned task",
                require_artifact=True,
            )

    def test_load_by_phase_returns_none_when_not_required(
        self, db_session, tenant, purpose_auto
    ):
        from ai_org_backend.services.artifact_resolver import load_by_phase

        result = load_by_phase(
            purpose_auto.id,
            "nonexistent phase",
            require_artifact=False,
        )
        assert result is None, "Should return None when require_artifact=False"

    def test_load_by_phase_raises_when_released_required_but_not(
        self, db_session, tenant, purpose_auto
    ):
        from ai_org_backend.services.artifact_resolver import (
            ArtifactNotFoundError,
            load_by_phase,
        )

        task = _make_task(
            db_session, tenant, purpose_auto, "Unreleased Phase", status="done"
        )
        _make_artifact(db_session, task, size=100, released=False)

        with pytest.raises(ArtifactNotFoundError, match="artifact not released"):
            load_by_phase(
                purpose_auto.id,
                "unreleased phase",
                require_artifact=True,
                require_released=True,
            )

    def test_artifact_not_found_error_attributes(self):
        from ai_org_backend.services.artifact_resolver import ArtifactNotFoundError

        err = ArtifactNotFoundError("vision document", "p-123", reason="test reason")
        assert err.phase == "vision document"
        assert err.purpose_id == "p-123"
        assert err.reason == "test reason"
        assert "vision document" in str(err)
        assert "p-123" in str(err)
        assert "test reason" in str(err)


# ──────────────────────────────────────────────────────────────────────
# S1-#12: Auto-mode approval gap in review_hook
# ──────────────────────────────────────────────────────────────────────


class TestReviewHookAutoModeGap:
    """Fix #12: _maybe_trigger_review must check for artifact existence
    even in auto mode, not just in manual mode."""

    def test_review_hook_blocks_when_artifact_missing_auto_mode(
        self, db_session, tenant, purpose_auto
    ):
        """Auto mode: blueprint task exists but no artifact → review should NOT trigger."""
        from ai_org_backend.hooks.review_hook import _maybe_trigger_review

        task = _make_task(
            db_session, tenant, purpose_auto, "Architecture Blueprint", status="done"
        )

        # Patch _ensure_review_task to verify it's NOT called
        with patch(
            "ai_org_backend.hooks.review_hook._ensure_review_task"
        ) as mock_ensure:
            _maybe_trigger_review(
                task_id=task.id,
                filename="blueprints/architecture_blueprint.md",
            )
            mock_ensure.assert_not_called()

    def test_review_hook_blocks_when_artifact_empty_auto_mode(
        self, db_session, tenant, purpose_auto
    ):
        """Auto mode: blueprint artifact has size=0 → review should NOT trigger."""
        from ai_org_backend.hooks.review_hook import _maybe_trigger_review

        task = _make_task(
            db_session, tenant, purpose_auto, "Architecture Blueprint", status="done"
        )
        _make_artifact(db_session, task, size=0, released=False)

        with patch(
            "ai_org_backend.hooks.review_hook._ensure_review_task"
        ) as mock_ensure:
            _maybe_trigger_review(
                task_id=task.id,
                filename="blueprints/architecture_blueprint.md",
            )
            mock_ensure.assert_not_called()

    def test_review_hook_proceeds_when_artifact_valid_auto_mode(
        self, db_session, tenant, purpose_auto
    ):
        """Auto mode: blueprint artifact valid → review should trigger."""
        from ai_org_backend.hooks.review_hook import _maybe_trigger_review

        task = _make_task(
            db_session, tenant, purpose_auto, "Architecture Blueprint", status="done"
        )
        _make_artifact(db_session, task, size=500, released=False)

        mock_review_task = MagicMock()
        mock_review_task.id = f"review-{uuid.uuid4().hex[:8]}"

        with (
            patch(
                "ai_org_backend.hooks.review_hook._ensure_review_task",
                return_value=mock_review_task,
            ) as mock_ensure,
            patch(
                "ai_org_backend.hooks.review_hook._wire_dependencies_after_blueprint"
            ),
            patch(
                "ai_org_backend.hooks.review_hook._schedule_reviewer_job"
            ),
            patch(
                "ai_org_backend.hooks.review_hook.SessionLocal"
            ) as mock_session_cls,
        ):
            # Mock the inner session query to return no existing artifact
            mock_s2 = MagicMock()
            mock_s2.query.return_value.filter.return_value.first.return_value = None
            mock_session_cls.return_value.__enter__ = MagicMock(return_value=mock_s2)
            mock_session_cls.return_value.__exit__ = MagicMock(return_value=False)

            _maybe_trigger_review(
                task_id=task.id,
                filename="blueprints/architecture_blueprint.md",
            )
            mock_ensure.assert_called_once()

    def test_review_hook_still_blocks_manual_mode_unreleased(
        self, db_session, tenant, purpose_manual
    ):
        """Manual mode: blueprint artifact exists but not released → review should NOT trigger."""
        from ai_org_backend.hooks.review_hook import _maybe_trigger_review

        task = _make_task(
            db_session, tenant, purpose_manual, "Architecture Blueprint", status="done"
        )
        _make_artifact(db_session, task, size=500, released=False)

        with patch(
            "ai_org_backend.hooks.review_hook._ensure_review_task"
        ) as mock_ensure:
            _maybe_trigger_review(
                task_id=task.id,
                filename="blueprints/architecture_blueprint.md",
            )
            mock_ensure.assert_not_called()
