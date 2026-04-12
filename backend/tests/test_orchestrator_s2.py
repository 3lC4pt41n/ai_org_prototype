"""S2-07: Integration tests for Sprint 2 orchestrator hardening.

Tests cover:
- S2-01: Distributed Redis locks (phase_lock, task_dispatch_lock)
- S2-03: Optimistic locking (CAS update)
- S2-04: Stuck-task detection
- S2-05: Dead-letter queue
- S2-06: Worker heartbeat
- S2-08/S2-12: LLM error classification and fallback chains
"""

import time
import uuid
from datetime import datetime as dt, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

# ── Test DB setup ──


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
    """Redirect all DB operations to the in-memory test database."""
    import ai_org_backend.db as db_mod
    import ai_org_backend.orchestrator.cas as cas_mod
    import ai_org_backend.orchestrator.watchdog as wd_mod

    monkeypatch.setattr(db_mod, "engine", test_engine)
    monkeypatch.setattr(cas_mod, "engine", test_engine)
    monkeypatch.setattr(wd_mod, "engine", test_engine)


@pytest.fixture
def db_session(test_engine):
    with Session(test_engine) as session:
        yield session


@pytest.fixture
def tenant(db_session):
    from ai_org_backend.models import Tenant

    t = Tenant(id="test-tenant", name="Test", email="t@t.com", hashed_password="x")
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)
    return t


@pytest.fixture
def task(db_session, tenant):
    from ai_org_backend.models import Task

    t = Task(
        id=str(uuid.uuid4())[:8],
        tenant_id=tenant.id,
        description="Test task",
        status="todo",
        version=0,
        created_at=dt.utcnow(),
    )
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)
    return t


# ──────────────────────────────────────────────────────────────────────
# S2-01: Redis Lock Tests
# ──────────────────────────────────────────────────────────────────────


class TestRedisLocks:
    def test_phase_lock_without_redis(self, monkeypatch):
        """When Redis is None, locks degrade gracefully (always acquired)."""
        import ai_org_backend.orchestrator.locks as locks_mod

        monkeypatch.setattr(locks_mod, "pool", None)

        from ai_org_backend.orchestrator.locks import phase_lock

        with phase_lock("t1", "p1", "arch") as acquired:
            assert acquired is True

    def test_phase_lock_with_mock_redis(self, monkeypatch):
        """Lock is acquired when Redis SET NX succeeds."""
        import ai_org_backend.orchestrator.locks as locks_mod

        mock_pool = MagicMock()
        mock_pool.set.return_value = True
        mock_pool.eval.return_value = 1
        monkeypatch.setattr(locks_mod, "pool", mock_pool)

        from ai_org_backend.orchestrator.locks import phase_lock

        with phase_lock("t1", "p1", "review") as acquired:
            assert acquired is True
            mock_pool.set.assert_called_once()

    def test_phase_lock_already_held(self, monkeypatch):
        """Lock not acquired when Redis SET NX returns False."""
        import ai_org_backend.orchestrator.locks as locks_mod

        mock_pool = MagicMock()
        mock_pool.set.return_value = False
        monkeypatch.setattr(locks_mod, "pool", mock_pool)

        from ai_org_backend.orchestrator.locks import phase_lock

        with phase_lock("t1", "p1", "planner") as acquired:
            assert acquired is False

    def test_task_dispatch_lock_dedup(self, monkeypatch):
        """Dispatch lock prevents double dispatch."""
        import ai_org_backend.orchestrator.locks as locks_mod

        mock_pool = MagicMock()
        call_count = 0

        def mock_set(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return call_count == 1  # Only first call succeeds

        mock_pool.set.side_effect = mock_set
        monkeypatch.setattr(locks_mod, "pool", mock_pool)

        from ai_org_backend.orchestrator.locks import task_dispatch_lock

        token1 = task_dispatch_lock("t1", "task-1")
        token2 = task_dispatch_lock("t1", "task-1")
        assert token1 is not None
        assert token2 is None


# ──────────────────────────────────────────────────────────────────────
# S2-03: Optimistic Locking Tests
# ──────────────────────────────────────────────────────────────────────


class TestOptimisticLocking:
    def test_cas_update_succeeds(self, task):
        from ai_org_backend.orchestrator.cas import cas_update_status

        new_ver = cas_update_status(task.id, 0, "doing")
        assert new_ver == 1

    def test_cas_update_rejects_stale_version(self, task):
        from ai_org_backend.orchestrator.cas import StaleTaskError, cas_update_status

        # First update succeeds (v0 → v1)
        cas_update_status(task.id, 0, "doing")

        # Second update with stale version (still expects v0) → fail
        with pytest.raises(StaleTaskError):
            cas_update_status(task.id, 0, "done")

    def test_cas_update_sequential(self, task):
        from ai_org_backend.orchestrator.cas import cas_update_status

        v1 = cas_update_status(task.id, 0, "doing")
        v2 = cas_update_status(task.id, v1, "done", notes="completed")
        assert v2 == 2


# ──────────────────────────────────────────────────────────────────────
# S2-04: Stuck Task Detection Tests
# ──────────────────────────────────────────────────────────────────────


class TestStuckTaskDetection:
    def test_detect_stuck_task(self, db_session, tenant):
        from ai_org_backend.models import Task
        from ai_org_backend.orchestrator.watchdog import detect_stuck_tasks

        # Create a task stuck in "doing" with old heartbeat
        stuck = Task(
            id=str(uuid.uuid4())[:8],
            tenant_id=tenant.id,
            description="Stuck task",
            status="doing",
            version=1,
            created_at=dt.utcnow() - timedelta(hours=1),
            last_heartbeat_at=dt.utcnow() - timedelta(minutes=20),
        )
        db_session.add(stuck)
        db_session.commit()

        stuck_ids = detect_stuck_tasks(tenant.id, threshold_s=900)
        assert stuck.id in stuck_ids

    def test_fresh_task_not_stuck(self, db_session, tenant):
        from ai_org_backend.models import Task
        from ai_org_backend.orchestrator.watchdog import detect_stuck_tasks

        fresh = Task(
            id=str(uuid.uuid4())[:8],
            tenant_id=tenant.id,
            description="Fresh task",
            status="doing",
            version=1,
            created_at=dt.utcnow(),
            last_heartbeat_at=dt.utcnow(),
        )
        db_session.add(fresh)
        db_session.commit()

        stuck_ids = detect_stuck_tasks(tenant.id, threshold_s=900)
        assert fresh.id not in stuck_ids

    def test_requeue_stuck_task(self, db_session, tenant, monkeypatch):
        from ai_org_backend.models import Task
        import ai_org_backend.orchestrator.watchdog as wd_mod

        monkeypatch.setattr(wd_mod, "pool", None)  # No Redis

        stuck = Task(
            id=str(uuid.uuid4())[:8],
            tenant_id=tenant.id,
            description="Will be requeued",
            status="doing",
            version=1,
            retries=0,
            created_at=dt.utcnow() - timedelta(hours=1),
            last_heartbeat_at=dt.utcnow() - timedelta(minutes=20),
        )
        db_session.add(stuck)
        db_session.commit()
        task_id = stuck.id

        from ai_org_backend.orchestrator.watchdog import requeue_stuck_tasks

        count = requeue_stuck_tasks(tenant.id, threshold_s=900)
        assert count >= 1

        db_session.expire_all()
        refreshed = db_session.get(Task, task_id)
        assert refreshed.status == "todo"
        assert refreshed.retries == 1


# ──────────────────────────────────────────────────────────────────────
# S2-05: Dead Letter Queue Tests
# ──────────────────────────────────────────────────────────────────────


class TestDeadLetterQueue:
    def test_move_to_dlq(self, db_session, tenant):
        from ai_org_backend.models import Task
        from ai_org_backend.orchestrator.watchdog import move_to_dlq

        task = Task(
            id=str(uuid.uuid4())[:8],
            tenant_id=tenant.id,
            description="DLQ candidate",
            status="failed",
            version=1,
            retries=3,
        )
        db_session.add(task)
        db_session.commit()
        task_id = task.id

        move_to_dlq(task_id, "test failure")

        db_session.expire_all()
        refreshed = db_session.get(Task, task_id)
        assert refreshed.status == "dead_letter"
        assert "DLQ:" in refreshed.notes

    def test_retry_dlq_task(self, db_session, tenant):
        from ai_org_backend.models import Task
        from ai_org_backend.orchestrator.watchdog import move_to_dlq, retry_dlq_task

        task = Task(
            id=str(uuid.uuid4())[:8],
            tenant_id=tenant.id,
            description="DLQ retry",
            status="failed",
            version=1,
            retries=3,
        )
        db_session.add(task)
        db_session.commit()
        task_id = task.id

        move_to_dlq(task_id, "exhausted")

        ok = retry_dlq_task(task_id)
        assert ok is True

        db_session.expire_all()
        refreshed = db_session.get(Task, task_id)
        assert refreshed.status == "todo"
        assert refreshed.retries == 0

    def test_stuck_task_moves_to_dlq_after_max_retries(self, db_session, tenant, monkeypatch):
        from ai_org_backend.models import Task
        import ai_org_backend.orchestrator.watchdog as wd_mod

        monkeypatch.setattr(wd_mod, "pool", None)

        stuck = Task(
            id=str(uuid.uuid4())[:8],
            tenant_id=tenant.id,
            description="Exhausted retries",
            status="doing",
            version=1,
            retries=3,  # Already at max
            created_at=dt.utcnow() - timedelta(hours=1),
            last_heartbeat_at=dt.utcnow() - timedelta(minutes=20),
        )
        db_session.add(stuck)
        db_session.commit()
        task_id = stuck.id

        from ai_org_backend.orchestrator.watchdog import requeue_stuck_tasks

        requeue_stuck_tasks(tenant.id, threshold_s=900)

        db_session.expire_all()
        refreshed = db_session.get(Task, task_id)
        assert refreshed.status == "dead_letter"


# ──────────────────────────────────────────────────────────────────────
# S2-06: Heartbeat Tests
# ──────────────────────────────────────────────────────────────────────


class TestHeartbeat:
    def test_record_heartbeat_updates_sql(self, db_session, task, monkeypatch):
        import ai_org_backend.orchestrator.watchdog as wd_mod

        monkeypatch.setattr(wd_mod, "pool", None)

        from ai_org_backend.orchestrator.watchdog import record_heartbeat

        assert task.last_heartbeat_at is None
        record_heartbeat(task.tenant_id, task.id)

        db_session.expire_all()
        refreshed = db_session.get(type(task), task.id)
        assert refreshed.last_heartbeat_at is not None

    def test_heartbeat_prevents_stuck_detection(self, db_session, tenant, monkeypatch):
        from ai_org_backend.models import Task
        import ai_org_backend.orchestrator.watchdog as wd_mod

        monkeypatch.setattr(wd_mod, "pool", None)

        task = Task(
            id=str(uuid.uuid4())[:8],
            tenant_id=tenant.id,
            description="Heartbeat task",
            status="doing",
            version=1,
            created_at=dt.utcnow() - timedelta(hours=1),
            last_heartbeat_at=dt.utcnow(),  # Fresh heartbeat
        )
        db_session.add(task)
        db_session.commit()

        from ai_org_backend.orchestrator.watchdog import detect_stuck_tasks

        stuck = detect_stuck_tasks(tenant.id, threshold_s=900)
        assert task.id not in stuck


# ──────────────────────────────────────────────────────────────────────
# S2-08/S2-12: LLM Error Classification Tests
# ──────────────────────────────────────────────────────────────────────


class TestLLMErrorHandling:
    def test_classify_rate_limit(self):
        from ai_org_backend.services.llm_errors import classify_error, ErrorCategory

        class MockResp:
            status_code = 429

        class RateErr(Exception):
            def __init__(self):
                self.response = MockResp()
                super().__init__("rate limited")

        cat = classify_error(RateErr())
        assert cat == ErrorCategory.RATE_LIMIT

    def test_classify_auth_error(self):
        from ai_org_backend.services.llm_errors import classify_error, ErrorCategory

        class MockResp:
            status_code = 401

        class AuthErr(Exception):
            def __init__(self):
                self.response = MockResp()
                super().__init__("unauthorized")

        cat = classify_error(AuthErr())
        assert cat == ErrorCategory.AUTH

    def test_classify_server_error(self):
        from ai_org_backend.services.llm_errors import classify_error, ErrorCategory

        class MockResp:
            status_code = 500

        class ServerErr(Exception):
            def __init__(self):
                self.response = MockResp()
                super().__init__("internal error")

        cat = classify_error(ServerErr())
        assert cat == ErrorCategory.SERVER

    def test_fallback_chain_resolution(self):
        from ai_org_backend.services.llm_errors import get_fallback_model

        fallback = get_fallback_model("gpt-4o")
        assert fallback is not None
        assert fallback != "gpt-4o"

    def test_fallback_chain_anthropic(self):
        from ai_org_backend.services.llm_errors import get_fallback_model

        fallback = get_fallback_model("claude-sonnet-4-20250514")
        assert fallback is not None

    def test_no_fallback_for_cheapest(self):
        from ai_org_backend.services.llm_errors import get_fallback_model

        fallback = get_fallback_model("gpt-3.5-turbo")
        assert fallback is None  # End of chain
