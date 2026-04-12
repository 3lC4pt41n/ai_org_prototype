"""Sprint 4 (Audit) integration tests: Multi-Agent Conflict Prevention & Validation.

Tests cover:
- S4-#25: Planner JSON Schema Enforcement (additionalProperties: false)
- S4-#10: Post-Assembly Build Validation (build_validator)
- S4-#8:  File-Ownership Reservation System (claim/release)
- S4-#23: Peer Context Hard Constraints (forbidden_files)
"""

# Python 3.10 compatibility shim
import enum
if not hasattr(enum, "StrEnum"):
    try:
        from strenum import StrEnum
        enum.StrEnum = StrEnum
    except ImportError:
        pass

import json
import tempfile
import uuid
from datetime import datetime as dt
from pathlib import Path
from unittest.mock import MagicMock, patch

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
    import ai_org_backend.models.file_reservation  # noqa: F401
    SQLModel.metadata.create_all(_engine)
    return _engine


@pytest.fixture(autouse=True)
def patch_engine(test_engine, monkeypatch):
    import ai_org_backend.db as db_mod
    monkeypatch.setattr(db_mod, "engine", test_engine)
    def _session_local():
        return Session(test_engine)
    monkeypatch.setattr(db_mod, "SessionLocal", _session_local)

    import ai_org_backend.services.file_reservation as fr_mod
    monkeypatch.setattr(fr_mod, "engine", test_engine)

    import ai_org_backend.services.peer_context as pc_mod
    monkeypatch.setattr(pc_mod, "engine", test_engine)


@pytest.fixture
def db_session(test_engine):
    with Session(test_engine) as session:
        yield session


@pytest.fixture
def tenant(db_session):
    from ai_org_backend.models import Tenant
    t = Tenant(
        id=f"t-s4-{uuid.uuid4().hex[:6]}",
        name="Test S4",
        email="s4@test.com",
        hashed_password="x",
    )
    db_session.add(t)
    db_session.commit()
    return t


@pytest.fixture
def purpose(db_session, tenant):
    from ai_org_backend.models import Purpose
    p = Purpose(
        id=f"p-s4-{uuid.uuid4().hex[:6]}",
        tenant_id=tenant.id,
        name="Test Purpose S4",
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


# ──────────────────────────────────────────────────────────────────────
# S4-#25: Planner JSON Schema Enforcement
# ──────────────────────────────────────────────────────────────────────


class TestPlannerSchemaEnforcement:
    """Fix #25: Planner schema rejects extra fields and retry includes schema."""

    def test_additional_properties_false(self):
        """TASKS_SCHEMA items must have additionalProperties: False."""
        from ai_org_backend.agents.planner import TASKS_SCHEMA
        items = TASKS_SCHEMA["items"]
        assert items.get("additionalProperties") is False, (
            "TASKS_SCHEMA items must have additionalProperties: False"
        )

    def test_schema_rejects_extra_fields(self):
        """Tasks with unexpected fields are rejected by jsonschema."""
        from jsonschema import validate, ValidationError
        from ai_org_backend.agents.planner import TASKS_SCHEMA

        valid_task = [{
            "id": "t1",
            "description": "Implement auth",
            "depends_on": None,
            "business_value": 5.0,
            "tokens_plan": 1000,
            "purpose_relevance": 0.8,
        }]
        # Should pass
        validate(instance=valid_task, schema=TASKS_SCHEMA)

        invalid_task = [{
            "id": "t1",
            "description": "Implement auth",
            "depends_on": None,
            "business_value": 5.0,
            "tokens_plan": 1000,
            "purpose_relevance": 0.8,
            "unexpected_field": "should be rejected",
        }]
        with pytest.raises(ValidationError):
            validate(instance=invalid_task, schema=TASKS_SCHEMA)

    def test_retry_error_note_includes_schema(self):
        """Planner retry path includes full schema in error_note."""
        import inspect
        from ai_org_backend.agents import planner as pl_mod
        source = inspect.getsource(pl_mod)
        assert "TASKS_SCHEMA" in source
        assert "schema_hint" in source or "json.dumps(TASKS_SCHEMA" in source, (
            "Retry path must include full schema dump in error_note"
        )

    def test_schema_allows_optional_fields(self):
        """Tasks with optional agent_role/model_name fields pass validation."""
        from jsonschema import validate
        from ai_org_backend.agents.planner import TASKS_SCHEMA

        task_with_optional = [{
            "id": "t2",
            "description": "Build API",
            "depends_on": "t1",
            "business_value": 3.0,
            "tokens_plan": 500,
            "purpose_relevance": 0.6,
            "agent_role": "dev",
            "model_name": "o3",
        }]
        validate(instance=task_with_optional, schema=TASKS_SCHEMA)


# ──────────────────────────────────────────────────────────────────────
# S4-#10: Post-Assembly Build Validation
# ──────────────────────────────────────────────────────────────────────


class TestBuildValidator:
    """Fix #10: Generated code is validated for syntax errors."""

    def test_valid_python_passes(self):
        """Valid Python files pass validation."""
        from ai_org_backend.services.build_validator import validate_files_content

        files = [{"path": "app.py", "content": "def hello():\n    return 'world'\n"}]
        report = validate_files_content(files)
        assert report.is_valid

    def test_invalid_python_fails(self):
        """Python files with syntax errors fail validation."""
        from ai_org_backend.services.build_validator import validate_files_content

        files = [{"path": "broken.py", "content": "def foo(\n    pass\n"}]
        report = validate_files_content(files)
        assert not report.is_valid
        assert any("syntax" in e.lower() or "broken.py" in e for e in report.errors)

    def test_valid_json_passes(self):
        """Valid JSON files pass validation."""
        from ai_org_backend.services.build_validator import validate_files_content

        files = [{"path": "config.json", "content": '{"key": "value"}'}]
        report = validate_files_content(files)
        assert report.is_valid

    def test_invalid_json_fails(self):
        """Invalid JSON files fail validation."""
        from ai_org_backend.services.build_validator import validate_files_content

        files = [{"path": "bad.json", "content": "{key: value}"}]
        report = validate_files_content(files)
        assert not report.is_valid
        assert any("bad.json" in e for e in report.errors)

    def test_validate_repository_on_directory(self):
        """validate_repository checks all .py and .json files in a directory."""
        from ai_org_backend.services.build_validator import validate_repository

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "valid.py").write_text("x = 1\n")
            (Path(tmpdir) / "valid.json").write_text('{"a": 1}')
            report = validate_repository(tmpdir)
        assert report.is_valid

    def test_validate_repository_nonexistent_path(self):
        """validate_repository errors for nonexistent paths."""
        from ai_org_backend.services.build_validator import validate_repository

        report = validate_repository("/nonexistent/path")
        assert not report.is_valid

    def test_repo_composer_has_build_validation(self):
        """repo_composer.py includes build validation after file creation."""
        src_path = Path(__file__).resolve().parent.parent / "ai_org_backend" / "agents" / "repo_composer.py"
        source = src_path.read_text(encoding="utf-8")
        assert "validate_files_content" in source, (
            "repo_composer must call validate_files_content"
        )
        assert "is_valid" in source, (
            "repo_composer must check validation report is_valid"
        )


# ──────────────────────────────────────────────────────────────────────
# S4-#8: File-Ownership Reservation System
# ──────────────────────────────────────────────────────────────────────


class TestFileReservation:
    """Fix #8: File ownership prevents concurrent writes to same files."""

    def test_claim_files_success(self, db_session, tenant, purpose):
        """First claim on a file succeeds."""
        from ai_org_backend.services.file_reservation import claim_files

        task = _make_task(db_session, tenant, purpose, "Dev Task A")
        result = claim_files(task.id, ["src/app.py", "src/db.py"], purpose.id,
                             session=db_session)
        db_session.commit()
        assert result is True

    def test_claim_files_conflict(self, db_session, tenant, purpose):
        """Second claim on same file by different task is rejected."""
        from ai_org_backend.services.file_reservation import claim_files

        task1 = _make_task(db_session, tenant, purpose, "Dev Task 1")
        task2 = _make_task(db_session, tenant, purpose, "Dev Task 2")

        ok1 = claim_files(task1.id, ["src/main.py"], purpose.id, session=db_session)
        db_session.commit()
        assert ok1 is True

        ok2 = claim_files(task2.id, ["src/main.py"], purpose.id, session=db_session)
        assert ok2 is False

    def test_claim_files_same_task_idempotent(self, db_session, tenant, purpose):
        """Claiming same files by same task is idempotent."""
        from ai_org_backend.services.file_reservation import claim_files

        task = _make_task(db_session, tenant, purpose, "Dev Task Idem")
        claim_files(task.id, ["src/util.py"], purpose.id, session=db_session)
        db_session.commit()

        # Second claim by same task should succeed
        ok = claim_files(task.id, ["src/util.py"], purpose.id, session=db_session)
        assert ok is True

    def test_release_files(self, db_session, tenant, purpose):
        """Releasing files allows another task to claim them."""
        from ai_org_backend.services.file_reservation import claim_files, release_files

        task1 = _make_task(db_session, tenant, purpose, "Dev Release 1")
        task2 = _make_task(db_session, tenant, purpose, "Dev Release 2")

        claim_files(task1.id, ["src/api.py"], purpose.id, session=db_session)
        db_session.commit()

        # task2 can't claim yet
        assert claim_files(task2.id, ["src/api.py"], purpose.id, session=db_session) is False

        # Release task1's claim
        release_files(task1.id, session=db_session)
        db_session.commit()

        # Now task2 can claim
        assert claim_files(task2.id, ["src/api.py"], purpose.id, session=db_session) is True

    def test_claim_empty_list_succeeds(self, db_session, tenant, purpose):
        """Claiming empty file list succeeds."""
        from ai_org_backend.services.file_reservation import claim_files

        task = _make_task(db_session, tenant, purpose, "Dev Empty")
        assert claim_files(task.id, [], purpose.id, session=db_session) is True


# ──────────────────────────────────────────────────────────────────────
# S4-#23: Peer Context Hard Constraints
# ──────────────────────────────────────────────────────────────────────


class TestPeerContextHardConstraints:
    """Fix #23: PeerContext includes forbidden_files as mandatory constraint."""

    def test_forbidden_files_field_exists(self):
        """PeerContext has forbidden_files field."""
        from ai_org_backend.services.peer_context import PeerContext
        ctx = PeerContext()
        assert hasattr(ctx, "forbidden_files")
        assert ctx.forbidden_files == []

    def test_forbidden_files_in_prompt(self):
        """forbidden_files render as HARD CONSTRAINT in prompt text."""
        from ai_org_backend.services.peer_context import PeerContext

        ctx = PeerContext(forbidden_files=["src/app.py", "src/db.py"])
        text = ctx.to_prompt_text()
        assert "FORBIDDEN" in text
        assert "HARD CONSTRAINT" in text or "DARFST NICHT" in text
        assert "src/app.py" in text
        assert "src/db.py" in text

    def test_empty_forbidden_files_no_section(self):
        """No forbidden section when no forbidden files."""
        from ai_org_backend.services.peer_context import PeerContext

        ctx = PeerContext()
        text = ctx.to_prompt_text()
        assert "FORBIDDEN" not in text

    def test_get_peer_context_loads_reservations(self, db_session, tenant, purpose):
        """get_peer_context includes forbidden_files from FileReservation."""
        from ai_org_backend.services.file_reservation import claim_files
        from ai_org_backend.services.peer_context import get_peer_context

        task1 = _make_task(db_session, tenant, purpose, "Dev Owner", status="doing")
        task2 = _make_task(db_session, tenant, purpose, "Dev Querying", status="doing")

        claim_files(task1.id, ["src/models.py", "src/views.py"], purpose.id,
                    session=db_session)
        db_session.commit()

        # task2 queries peer context — should see task1's files as forbidden
        ctx = get_peer_context(purpose.id, exclude_task_id=task2.id)
        assert "src/models.py" in ctx.forbidden_files
        assert "src/views.py" in ctx.forbidden_files

    def test_peer_context_source_has_file_reservation_import(self):
        """peer_context.py imports and uses get_claimed_files."""
        import inspect
        from ai_org_backend.services import peer_context as pc_mod
        source = inspect.getsource(pc_mod.get_peer_context)
        assert "get_claimed_files" in source or "file_reservation" in source
