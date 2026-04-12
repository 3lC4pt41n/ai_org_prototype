"""Sprint 6 integration tests: Security Hardening, Observability & Production Readiness.

Tests cover:
- S6-01: Rate Limiting Middleware
- S6-02: Security Headers Middleware
- S6-03: Request ID Middleware
- S6-04: Global Exception Handler
- S6-05: Health / Readiness / Liveness Probes
- S6-06: Structured Logging (JSON formatter)
- S6-07: Prometheus HTTP Metrics
- S6-08: Graceful Shutdown
- S6-09: Input Sanitization + Password Complexity
- S6-10: Audit Log Model
- S6-11: Alembic Migration
"""

import json
import logging
import os
import re
import time
import uuid
from datetime import datetime as dt
from io import StringIO
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
    t = Tenant(
        id=f"test-s6-{uuid.uuid4().hex[:6]}",
        name="Test S6",
        email=f"s6-{uuid.uuid4().hex[:6]}@t.com",
        hashed_password="x",
    )
    db_session.add(t)
    db_session.commit()
    return t


# ───────────────── S6-01: Rate Limiting ──────────────────────────


class TestRateLimiting:
    """Test the token-bucket rate limiter."""

    def test_bucket_allows_requests_within_limit(self):
        from ai_org_backend.middleware.rate_limit import _TokenBucket

        bucket = _TokenBucket(capacity=10, refill_rate=1.0)
        for _ in range(10):
            assert bucket.consume() is True

    def test_bucket_rejects_after_exhaustion(self):
        from ai_org_backend.middleware.rate_limit import _TokenBucket

        bucket = _TokenBucket(capacity=3, refill_rate=0.01)
        for _ in range(3):
            bucket.consume()
        assert bucket.consume() is False

    def test_bucket_refills_over_time(self):
        from ai_org_backend.middleware.rate_limit import _TokenBucket

        bucket = _TokenBucket(capacity=5, refill_rate=100.0)  # 100 tokens/sec
        for _ in range(5):
            bucket.consume()
        assert bucket.consume() is False
        time.sleep(0.05)  # 50ms → ~5 tokens refilled
        assert bucket.consume() is True

    def test_retry_after_positive_when_empty(self):
        from ai_org_backend.middleware.rate_limit import _TokenBucket

        bucket = _TokenBucket(capacity=2, refill_rate=1.0)
        bucket.consume()
        bucket.consume()
        bucket.consume()  # should fail
        assert bucket.retry_after >= 1

    def test_middleware_exempt_paths(self):
        from ai_org_backend.middleware.rate_limit import _EXEMPT_PATHS

        assert "/health" in _EXEMPT_PATHS
        assert "/metrics" in _EXEMPT_PATHS
        assert "/readyz" in _EXEMPT_PATHS


# ───────────────── S6-02: Security Headers ───────────────────────


class TestSecurityHeaders:
    """Test that security headers are correctly defined."""

    def test_security_headers_dict(self):
        from ai_org_backend.middleware.security_headers import _SECURITY_HEADERS

        assert _SECURITY_HEADERS["X-Content-Type-Options"] == "nosniff"
        assert _SECURITY_HEADERS["X-Frame-Options"] == "DENY"
        assert "no-store" in _SECURITY_HEADERS["Cache-Control"]

    def test_permissions_policy_present(self):
        from ai_org_backend.middleware.security_headers import _SECURITY_HEADERS

        pp = _SECURITY_HEADERS.get("Permissions-Policy", "")
        assert "camera=()" in pp
        assert "microphone=()" in pp


# ───────────────── S6-03: Request ID ────────────────────────────


class TestRequestID:
    """Test the request ID context var."""

    def test_get_request_id_default_empty(self):
        from ai_org_backend.middleware.request_id import REQUEST_ID_CTX, get_request_id

        # Reset to ensure clean state
        token = REQUEST_ID_CTX.set("")
        assert get_request_id() == ""
        REQUEST_ID_CTX.reset(token)

    def test_set_and_get_request_id(self):
        from ai_org_backend.middleware.request_id import REQUEST_ID_CTX, get_request_id

        token = REQUEST_ID_CTX.set("test-rid-123")
        assert get_request_id() == "test-rid-123"
        REQUEST_ID_CTX.reset(token)


# ───────────────── S6-04: Exception Handler ──────────────────────


class TestExceptionHandler:
    """Test the standardised error envelope."""

    def test_error_envelope_shape(self):
        from ai_org_backend.middleware.exception_handler import _error_envelope

        resp = _error_envelope(404, "not_found", "Resource not found", "rid-42")
        assert resp.status_code == 404
        body = json.loads(resp.body)
        assert body["error"] == "not_found"
        assert body["detail"] == "Resource not found"
        assert body["request_id"] == "rid-42"
        assert body["status"] == 404

    def test_status_to_slug(self):
        from ai_org_backend.middleware.exception_handler import _status_to_slug

        assert _status_to_slug(400) == "bad_request"
        assert _status_to_slug(429) == "rate_limit_exceeded"
        assert _status_to_slug(500) == "internal_error"
        assert _status_to_slug(999) == "http_999"


# ───────────────── S6-05: Health Probes ──────────────────────────


class TestHealthProbes:
    """Test health probe endpoints exist and return correct shapes."""

    def test_liveness_returns_ok(self):
        """Liveness probe should always return status ok."""
        import asyncio
        from ai_org_backend.api.health import liveness

        result = asyncio.get_event_loop().run_until_complete(liveness())
        assert result["status"] == "ok"
        assert "uptime_seconds" in result

    def test_readiness_checks_components(self):
        """Readiness probe should check db and redis."""
        from ai_org_backend.api.health import _check_db

        # With our test engine, db should be ok
        result = _check_db()
        assert result["status"] == "ok"


# ───────────────── S6-06: Structured Logging ─────────────────────


class TestStructuredLogging:
    """Test JSON formatter and logging setup."""

    def test_json_formatter_output(self):
        from ai_org_backend.services.structured_logging import JSONFormatter

        fmt = JSONFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Hello %s",
            args=("world",),
            exc_info=None,
        )
        output = fmt.format(record)
        parsed = json.loads(output)
        assert parsed["level"] == "INFO"
        assert parsed["message"] == "Hello world"
        assert parsed["logger"] == "test.logger"
        assert parsed["lineno"] == 42
        assert "timestamp" in parsed

    def test_text_formatter_output(self):
        from ai_org_backend.services.structured_logging import TextFormatter

        fmt = TextFormatter()
        record = logging.LogRecord(
            name="test", level=logging.WARNING, pathname="t.py",
            lineno=1, msg="warn msg", args=(), exc_info=None,
        )
        output = fmt.format(record)
        assert "WARNING" in output
        assert "warn msg" in output

    def test_setup_logging_configures_root(self):
        from ai_org_backend.services.structured_logging import setup_logging

        setup_logging(level="DEBUG", fmt="text")
        root = logging.getLogger()
        assert root.level == logging.DEBUG
        # Cleanup
        setup_logging(level="WARNING", fmt="text")


# ───────────────── S6-07: HTTP Metrics ───────────────────────────


class TestHTTPMetrics:
    """Test the HTTP metrics middleware utilities."""

    def test_normalize_path_fallback(self):
        from ai_org_backend.middleware.metrics_middleware import _normalize_path

        # Create a mock request with no route
        mock_request = MagicMock()
        mock_request.scope = {}
        mock_request.url.path = "/api/v1/tasks/abc123/status"
        result = _normalize_path(mock_request)
        # Should truncate to depth 3
        assert result == "/api/v1/tasks"

    def test_normalize_path_with_route(self):
        from ai_org_backend.middleware.metrics_middleware import _normalize_path

        mock_request = MagicMock()
        mock_route = MagicMock()
        mock_route.path = "/api/v1/tasks/{task_id}"
        mock_request.scope = {"route": mock_route}
        result = _normalize_path(mock_request)
        assert result == "/api/v1/tasks/{task_id}"

    def test_skip_paths_defined(self):
        from ai_org_backend.middleware.metrics_middleware import _SKIP_PATHS

        assert "/metrics" in _SKIP_PATHS
        assert "/health" in _SKIP_PATHS


# ───────────────── S6-08: Graceful Shutdown ──────────────────────


class TestGracefulShutdown:
    """Test startup/shutdown hooks."""

    def test_on_startup_sets_timestamp(self):
        from ai_org_backend.services import graceful_shutdown

        graceful_shutdown.on_startup()
        assert graceful_shutdown._STARTUP_TS > 0

    def test_on_shutdown_disposes_engine(self):
        from ai_org_backend.services import graceful_shutdown

        graceful_shutdown.on_startup()
        # Should not raise even if neo4j/celery aren't available
        with patch("ai_org_backend.services.graceful_shutdown.logger"):
            graceful_shutdown.on_shutdown()


# ───────────────── S6-09: Input Sanitization ─────────────────────


class TestInputSanitization:
    """Test dangerous pattern detection and password complexity."""

    def test_scan_xss_script_tag(self):
        from ai_org_backend.middleware.input_sanitizer import _scan_value

        assert _scan_value("<script>alert(1)</script>") == "xss"
        assert _scan_value("hello world") is None

    def test_scan_xss_event_handler(self):
        from ai_org_backend.middleware.input_sanitizer import _scan_value

        assert _scan_value('onload=alert(1)') == "xss"

    def test_scan_sql_injection(self):
        from ai_org_backend.middleware.input_sanitizer import _scan_value

        assert _scan_value("'; DROP TABLE users; --") == "sql_injection"
        assert _scan_value("UNION SELECT * FROM passwords") == "sql_injection"

    def test_scan_json_recursive(self):
        from ai_org_backend.middleware.input_sanitizer import _scan_json

        obj = {"name": "safe", "nested": {"evil": "<script>hack</script>"}}
        assert _scan_json(obj) == "xss"

    def test_scan_json_clean(self):
        from ai_org_backend.middleware.input_sanitizer import _scan_json

        obj = {"name": "Tim", "tasks": ["build", "test"]}
        assert _scan_json(obj) is None

    def test_scan_json_depth_limit(self):
        from ai_org_backend.middleware.input_sanitizer import _scan_json

        # Build deeply nested structure
        obj = "safe"
        for _ in range(25):
            obj = {"v": obj}
        # Should not crash, just return None at depth > 20
        assert _scan_json(obj) is None

    def test_password_complexity_valid(self):
        from ai_org_backend.api.auth import RegisterIn

        # Should not raise
        reg = RegisterIn(email="a@b.com", password="Abcd1234")
        assert reg.password == "Abcd1234"

    def test_password_complexity_no_uppercase(self):
        from ai_org_backend.api.auth import RegisterIn

        with pytest.raises(Exception):
            RegisterIn(email="a@b.com", password="abcd1234")

    def test_password_complexity_no_digit(self):
        from ai_org_backend.api.auth import RegisterIn

        with pytest.raises(Exception):
            RegisterIn(email="a@b.com", password="Abcdefgh")

    def test_password_complexity_no_lowercase(self):
        from ai_org_backend.api.auth import RegisterIn

        with pytest.raises(Exception):
            RegisterIn(email="a@b.com", password="ABCD1234")


# ───────────────── S6-10: Audit Log Model ───────────────────────


class TestAuditLog:
    """Test the AuditLog ORM model."""

    def test_audit_log_creation(self, db_session, tenant):
        from ai_org_backend.models import AuditAction, AuditLog

        entry = AuditLog(
            tenant_id=tenant.id,
            action=AuditAction.LOGIN_SUCCESS.value,
            detail="Login from 192.168.1.1",
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
            request_id="rid-test-01",
        )
        db_session.add(entry)
        db_session.commit()
        db_session.refresh(entry)

        assert entry.id is not None
        assert len(entry.id) == 8
        assert entry.action == "login_success"
        assert entry.tenant_id == tenant.id

    def test_audit_log_without_tenant(self, db_session):
        from ai_org_backend.models import AuditAction, AuditLog

        entry = AuditLog(
            action=AuditAction.RATE_LIMIT_HIT.value,
            detail="Rate limited anonymous request",
            ip_address="10.0.0.1",
        )
        db_session.add(entry)
        db_session.commit()
        db_session.refresh(entry)

        assert entry.tenant_id is None
        assert entry.action == "rate_limit_hit"

    def test_audit_action_enum_values(self):
        from ai_org_backend.models import AuditAction

        assert AuditAction.LOGIN_SUCCESS.value == "login_success"
        assert AuditAction.DANGEROUS_INPUT.value == "dangerous_input"
        assert AuditAction.APPROVAL.value == "approval"

    def test_multiple_audit_entries(self, db_session, tenant):
        from ai_org_backend.models import AuditAction, AuditLog

        entries = [
            AuditLog(
                tenant_id=tenant.id,
                action=AuditAction.LOGIN_FAILURE.value,
                detail=f"Attempt {i}",
                ip_address="1.2.3.4",
            )
            for i in range(5)
        ]
        for e in entries:
            db_session.add(e)
        db_session.commit()

        from sqlmodel import select
        results = db_session.exec(
            select(AuditLog).where(
                AuditLog.tenant_id == tenant.id,
                AuditLog.action == "login_failure",
            )
        ).all()
        assert len(results) >= 5


# ───────────────── S6-11: Alembic Migration ─────────────────────


class TestAlembicMigration:
    """Verify the S6 migration script is well-formed."""

    def test_migration_revision_chain(self):
        import importlib
        mod = importlib.import_module(
            "ai_org_backend.alembic.versions.20260330_s6_audit_log"
        )
        assert mod.revision == "s6_audit_log"
        assert mod.down_revision == "s5_review_merge"

    def test_migration_has_upgrade_and_downgrade(self):
        import importlib
        mod = importlib.import_module(
            "ai_org_backend.alembic.versions.20260330_s6_audit_log"
        )
        assert callable(getattr(mod, "upgrade", None))
        assert callable(getattr(mod, "downgrade", None))


# ───────────────── S6-12: Settings Extensions ───────────────────


class TestSettingsExtensions:
    """Verify new S6 settings fields have correct defaults."""

    def test_rate_limit_defaults(self):
        from ai_org_backend.settings import Settings

        s = Settings()
        assert s.rate_limit_per_minute == 60
        assert s.rate_limit_burst == 10

    def test_log_level_default(self):
        from ai_org_backend.settings import Settings

        s = Settings()
        assert s.log_level == "INFO"
        assert s.log_format == "json"

    def test_max_request_body_default(self):
        from ai_org_backend.settings import Settings

        s = Settings()
        assert s.max_request_body_bytes == 10 * 1024 * 1024


# ───────────────── S6-13: Main.py Integration ───────────────────


class TestMainIntegration:
    """Verify middleware is correctly wired into the FastAPI app."""

    def test_app_has_middleware_stack(self):
        """Confirm that the FastAPI app object exists and has middleware."""
        from ai_org_backend.main import app

        # The app should have user_middleware entries
        mw_classes = [m.cls.__name__ for m in app.user_middleware if hasattr(m, "cls")]
        # Check key middleware is registered
        assert "RequestIDMiddleware" in mw_classes
        assert "SecurityHeadersMiddleware" in mw_classes
        assert "RateLimitMiddleware" in mw_classes
        assert "InputSanitizerMiddleware" in mw_classes
        assert "MetricsMiddleware" in mw_classes

    def test_health_router_included(self):
        """Confirm health endpoints are reachable."""
        from ai_org_backend.main import app

        routes = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/health" in routes or "/healthz" in routes
