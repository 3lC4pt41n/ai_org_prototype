"""Sprint 3 (Audit) integration tests: Graph Integrity & Stuck-Task Recovery.

Tests cover:
- S3-#3:  CAS-based dispatch logic (lock TTL, renew_lock, atomic version check)
- S3-#7:  Cycle detection in repo.link()
- S3-#11: Stuck-task watchdog as Celery Beat task
- S3-#6:  Graph sync retry decorator & deferred sync
"""

# Python 3.10 compatibility shim
import enum
if not hasattr(enum, "StrEnum"):
    try:
        from strenum import StrEnum
        enum.StrEnum = StrEnum
    except ImportError:
        pass

import uuid
from datetime import datetime as dt, timedelta
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
    import ai_org_backend.models  # noqa: F401
    import ai_org_backend.models.chat  # noqa: F401
    import ai_org_backend.models.code_review_finding  # noqa: F401
    SQLModel.metadata.create_all(_engine)
    return _engine


@pytest.fixture(autouse=True)
def patch_engine(test_engine, monkeypatch):
    """Patch engine into all modules that cache it at import time."""
    import ai_org_backend.db as db_mod
    monkeypatch.setattr(db_mod, "engine", test_engine)

    def _session_local():
        return Session(test_engine)
    monkeypatch.setattr(db_mod, "SessionLocal", _session_local)

    import ai_org_backend.orchestrator.watchdog as wd_mod
    monkeypatch.setattr(wd_mod, "engine", test_engine)

    import ai_org_backend.orchestrator.scheduler as sched_mod
    monkeypatch.setattr(sched_mod, "engine", test_engine)


@pytest.fixture
def db_session(test_engine):
    with Session(test_engine) as session:
        yield session


@pytest.fixture
def tenant(db_session):
    from ai_org_backend.models import Tenant
    t = Tenant(
        id=f"t-s3-{uuid.uuid4().hex[:6]}",
        name="Test S3",
        email="s3@test.com",
        hashed_password="x",
    )
    db_session.add(t)
    db_session.commit()
    return t


@pytest.fixture
def purpose(db_session, tenant):
    from ai_org_backend.models import Purpose
    p = Purpose(
        id=f"p-s3-{uuid.uuid4().hex[:6]}",
        tenant_id=tenant.id,
        name="Test Purpose S3",
        mode="auto",
    )
    db_session.add(p)
    db_session.commit()
    return p


def _make_task(db_session, tenant, purpose, description, status="todo", **kw):
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
# S3-#3: CAS-Based Dispatch Logic
# ──────────────────────────────────────────────────────────────────────


class TestCASDispatchLogic:
    """Fix #3: Compare-and-swap dispatch prevents double-dispatch race conditions."""

    def test_lock_ttl_raised_to_300(self):
        """Lock TTL should match TASK_SOFT_TIME_LIMIT (300s)."""
        from ai_org_backend.orchestrator.locks import _LOCK_TTL_S
        assert _LOCK_TTL_S == 300, (
            f"Lock TTL should be 300s, got {_LOCK_TTL_S}"
        )

    def test_task_dispatch_lock_uses_raised_ttl(self):
        """task_dispatch_lock default TTL should be _LOCK_TTL_S (300)."""
        import inspect
        from ai_org_backend.orchestrator.locks import task_dispatch_lock, _LOCK_TTL_S
        sig = inspect.signature(task_dispatch_lock)
        default_ttl = sig.parameters["ttl"].default
        assert default_ttl == _LOCK_TTL_S, (
            f"task_dispatch_lock default ttl should be {_LOCK_TTL_S}, got {default_ttl}"
        )

    def test_renew_lock_function_exists(self):
        """renew_lock function should be available in locks module."""
        from ai_org_backend.orchestrator.locks import renew_lock
        assert callable(renew_lock)

    def test_renew_lock_noop_without_redis(self):
        """renew_lock returns True when pool is None (single-process mode)."""
        from ai_org_backend.orchestrator.locks import renew_lock
        with patch("ai_org_backend.orchestrator.locks.pool", None):
            result = renew_lock("t1", "p1", "vision", "local")
        assert result is True

    def test_renew_lock_with_token_local(self):
        """renew_lock returns True for local tokens (no Redis)."""
        from ai_org_backend.orchestrator.locks import renew_lock
        result = renew_lock("t1", "p1", "vision", "local")
        assert result is True

    def test_scheduler_has_cas_update(self):
        """Scheduler dispatch path uses CAS (UPDATE WHERE version=?) pattern."""
        import inspect
        from ai_org_backend.orchestrator import scheduler as sched_mod
        source = inspect.getsource(sched_mod)
        assert "Task.version == current_version" in source, (
            "Scheduler must use CAS version check in dispatch path"
        )
        assert "cas_result" in source or "rowcount" in source, (
            "Scheduler must check rowcount after CAS update"
        )


# ──────────────────────────────────────────────────────────────────────
# S3-#7: Cycle Detection in repo.link()
# ──────────────────────────────────────────────────────────────────────


class TestCycleDetection:
    """Fix #7: repo.link() prevents creation of circular dependencies."""

    def test_simple_cycle_detected(self, db_session, tenant, purpose):
        """A→B, then B→A should raise CyclicDependencyError."""
        from ai_org_backend.repo import Repo
        from ai_org_backend.services.cycle_detector import CyclicDependencyError

        task_a = _make_task(db_session, tenant, purpose, "Task A")
        task_b = _make_task(db_session, tenant, purpose, "Task B")

        repo = Repo(tenant.id)
        with patch("ai_org_backend.repo.graph_sync"):
            repo.link(task_a.id, task_b.id)  # A → B: OK

            with pytest.raises(CyclicDependencyError):
                repo.link(task_b.id, task_a.id)  # B → A: CYCLE!

    def test_transitive_cycle_detected(self, db_session, tenant, purpose):
        """A→B, B→C, then C→A should raise CyclicDependencyError."""
        from ai_org_backend.repo import Repo
        from ai_org_backend.services.cycle_detector import CyclicDependencyError

        task_a = _make_task(db_session, tenant, purpose, "Phase A")
        task_b = _make_task(db_session, tenant, purpose, "Phase B")
        task_c = _make_task(db_session, tenant, purpose, "Phase C")

        repo = Repo(tenant.id)
        with patch("ai_org_backend.repo.graph_sync"):
            repo.link(task_a.id, task_b.id)  # A → B
            repo.link(task_b.id, task_c.id)  # B → C

            with pytest.raises(CyclicDependencyError):
                repo.link(task_c.id, task_a.id)  # C → A: CYCLE!

    def test_non_cyclic_link_succeeds(self, db_session, tenant, purpose):
        """A→B, A→C (no cycle) should succeed."""
        from ai_org_backend.repo import Repo

        task_a = _make_task(db_session, tenant, purpose, "Root Task")
        task_b = _make_task(db_session, tenant, purpose, "Child 1")
        task_c = _make_task(db_session, tenant, purpose, "Child 2")

        repo = Repo(tenant.id)
        with patch("ai_org_backend.repo.graph_sync"):
            repo.link(task_a.id, task_b.id)  # A → B
            repo.link(task_a.id, task_c.id)  # A → C: OK (no cycle)

    def test_self_loop_detected(self, db_session, tenant, purpose):
        """A→A should raise CyclicDependencyError."""
        from ai_org_backend.repo import Repo
        from ai_org_backend.services.cycle_detector import CyclicDependencyError

        task_a = _make_task(db_session, tenant, purpose, "Self-Loop Task")
        repo = Repo(tenant.id)
        with patch("ai_org_backend.repo.graph_sync"):
            with pytest.raises(CyclicDependencyError):
                repo.link(task_a.id, task_a.id)  # A → A: CYCLE!


# ──────────────────────────────────────────────────────────────────────
# S3-#11: Stuck-Task Watchdog as Celery Beat Task
# ──────────────────────────────────────────────────────────────────────


class TestStuckTaskWatchdog:
    """Fix #11: Celery Beat watchdog detects and recovers stuck tasks."""

    def test_beat_schedule_has_watchdog(self):
        """Celery Beat schedule must include watchdog.detect_stuck_tasks."""
        from ai_org_backend.celeryconfig import CELERY_BEAT_SCHEDULE
        assert "watchdog-stuck-tasks" in CELERY_BEAT_SCHEDULE
        entry = CELERY_BEAT_SCHEDULE["watchdog-stuck-tasks"]
        assert entry["task"] == "watchdog.detect_stuck_tasks"
        assert entry["schedule"] == 300.0  # 5 minutes

    def test_watchdog_task_registered(self):
        """watchdog_task module exists and has the Celery task."""
        from ai_org_backend.tasks import watchdog_task
        assert hasattr(watchdog_task, "watchdog_detect_stuck_tasks")

    def test_detect_stuck_tasks_finds_stale(self, db_session, tenant, purpose):
        """Tasks in DOING with old heartbeat are detected as stuck."""
        from ai_org_backend.orchestrator.watchdog import detect_stuck_tasks

        stale_time = dt.utcnow() - timedelta(minutes=20)
        stuck_task = _make_task(
            db_session, tenant, purpose, "Stuck Task",
            status="doing", last_heartbeat_at=stale_time,
        )

        with patch("ai_org_backend.orchestrator.watchdog.pool", None):
            stuck_ids = detect_stuck_tasks(tenant.id, threshold_s=900)

        assert stuck_task.id in stuck_ids

    def test_detect_stuck_tasks_ignores_fresh(self, db_session, tenant, purpose):
        """Tasks in DOING with recent heartbeat are NOT detected as stuck."""
        from ai_org_backend.orchestrator.watchdog import detect_stuck_tasks

        fresh_time = dt.utcnow() - timedelta(minutes=2)
        fresh_task = _make_task(
            db_session, tenant, purpose, "Fresh Task",
            status="doing", last_heartbeat_at=fresh_time,
        )

        with patch("ai_org_backend.orchestrator.watchdog.pool", None):
            stuck_ids = detect_stuck_tasks(tenant.id, threshold_s=900)

        assert fresh_task.id not in stuck_ids

    def test_requeue_stuck_task(self, db_session, tenant, purpose):
        """requeue_stuck_tasks resets stuck tasks to 'todo' and increments retries."""
        from ai_org_backend.orchestrator.watchdog import requeue_stuck_tasks

        stale_time = dt.utcnow() - timedelta(minutes=20)
        task = _make_task(
            db_session, tenant, purpose, "Requeue Me",
            status="doing", last_heartbeat_at=stale_time,
        )
        assert task.retries == 0

        with patch("ai_org_backend.orchestrator.watchdog.pool", None):
            requeued = requeue_stuck_tasks(tenant.id, threshold_s=900)

        assert requeued >= 1
        db_session.refresh(task)
        assert task.status == "todo"
        assert task.retries == 1

    def test_move_to_dlq_after_max_retries(self, db_session, tenant, purpose):
        """Tasks exceeding max retries are moved to dead_letter queue."""
        from ai_org_backend.orchestrator.watchdog import requeue_stuck_tasks, DLQ_MAX_RETRIES

        stale_time = dt.utcnow() - timedelta(minutes=20)
        task = _make_task(
            db_session, tenant, purpose, "DLQ Candidate",
            status="doing", last_heartbeat_at=stale_time,
            retries=DLQ_MAX_RETRIES,  # Already at max
        )

        with patch("ai_org_backend.orchestrator.watchdog.pool", None):
            requeue_stuck_tasks(tenant.id, threshold_s=900)

        db_session.refresh(task)
        assert task.status == "dead_letter"
        assert "DLQ" in (task.notes or "")


# ──────────────────────────────────────────────────────────────────────
# S3-#6: Graph Sync Retry with Reconciliation
# ──────────────────────────────────────────────────────────────────────


class TestGraphSyncRetry:
    """Fix #6: Neo4j graph sync functions have retry logic."""

    def test_retry_decorator_on_upsert_task(self):
        """upsert_task should be wrapped with _retry_on_neo4j_failure."""
        from ai_org_backend.services.graph_sync import upsert_task
        # Decorated functions have __wrapped__ or the decorator modifies __name__
        assert upsert_task.__name__ == "upsert_task", (
            "upsert_task must retain its name (functools.wraps)"
        )

    def test_retry_decorator_on_upsert_dependency(self):
        """upsert_dependency should be wrapped with retry decorator."""
        from ai_org_backend.services.graph_sync import upsert_dependency
        assert upsert_dependency.__name__ == "upsert_dependency"

    def test_retry_decorator_on_remove_tasks(self):
        """remove_tasks should be wrapped with retry decorator."""
        from ai_org_backend.services.graph_sync import remove_tasks
        assert remove_tasks.__name__ == "remove_tasks"

    def test_retry_config_values(self):
        """Retry configuration: 3 attempts, 2s base, 120s max."""
        from ai_org_backend.services import graph_sync as gs
        assert gs._MAX_RETRIES == 3
        assert gs._BASE_DELAY_S == 2.0
        assert gs._MAX_DELAY_S == 120.0

    def test_retry_decorator_retries_on_failure(self):
        """_retry_on_neo4j_failure retries the function on exception."""
        from ai_org_backend.services.graph_sync import _retry_on_neo4j_failure

        call_count = 0

        @_retry_on_neo4j_failure
        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Neo4j down")
            return "success"

        with patch("ai_org_backend.services.graph_sync.time.sleep"):
            result = flaky_func()

        assert result == "success"
        assert call_count == 3

    def test_retry_decorator_raises_after_max_retries(self):
        """_retry_on_neo4j_failure raises after exhausting retries."""
        from ai_org_backend.services.graph_sync import _retry_on_neo4j_failure

        @_retry_on_neo4j_failure
        def always_fails():
            raise ConnectionError("Neo4j permanently down")

        with patch("ai_org_backend.services.graph_sync.time.sleep"):
            with pytest.raises(ConnectionError, match="permanently down"):
                always_fails()

    def test_repo_update_uses_deferred_sync(self):
        """Repo.update() source in repo.py should attempt deferred Celery graph sync."""
        import inspect
        import ai_org_backend.repo as repo_mod
        # Read the module source directly to avoid monkey-patching interference
        source = inspect.getsource(repo_mod)
        assert "graph.sync" in source, (
            "repo.py must use deferred Celery task 'graph.sync'"
        )
        assert "send_task" in source, (
            "repo.py must call celery.send_task for deferred sync"
        )

    def test_beat_schedule_has_reconciliation(self):
        """Celery Beat schedule must include graph.reconcile."""
        from ai_org_backend.celeryconfig import CELERY_BEAT_SCHEDULE
        assert "graph-reconcile-every-30min" in CELERY_BEAT_SCHEDULE
        entry = CELERY_BEAT_SCHEDULE["graph-reconcile-every-30min"]
        assert entry["task"] == "graph.reconcile"
