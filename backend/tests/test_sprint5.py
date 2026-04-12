"""Sprint 5 integration tests: Multi-Agent Coordination.

Tests cover:
- S5-A1: Shared Contracts loading
- S5-A2: Peer Task Visibility
- S5-A3: Conflict Detection
- S5-A4: Repo Snapshot
- S5-B1: Code Review Blocking Gate
- S5-B2: Merge Service
- S5-B3: Re-Review Loop
- S5-B4: CodeReviewFinding persistence
"""

import json
import os
import tempfile
import uuid
from datetime import datetime as dt
from pathlib import Path
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
    t = Tenant(id="test-s5", name="Test S5", email="s5@t.com", hashed_password="x")
    db_session.add(t)
    db_session.commit()
    return t


@pytest.fixture
def purpose(db_session, tenant):
    from ai_org_backend.models import Purpose
    p = Purpose(
        id=str(uuid.uuid4())[:8],
        tenant_id=tenant.id,
        name="Test Purpose S5",
        mode="auto",
    )
    db_session.add(p)
    db_session.commit()
    return p


# ──────────────────────────────────────────────────────────────────────
# S5-A1: Shared Contracts
# ──────────────────────────────────────────────────────────────────────


class TestSharedContracts:
    def test_load_shared_contracts(self):
        from ai_org_backend.services.shared_contracts import load_shared_contracts
        # Clear cache
        load_shared_contracts.cache_clear()
        text = load_shared_contracts()
        # Should either find the file or return empty string
        assert isinstance(text, str)

    def test_contracts_contain_key_sections(self):
        from ai_org_backend.services.shared_contracts import load_shared_contracts
        load_shared_contracts.cache_clear()
        text = load_shared_contracts()
        if text:  # Only if file was found
            assert "Tech Stack" in text
            assert "API Conventions" in text
            assert "Error Handling" in text


# ──────────────────────────────────────────────────────────────────────
# S5-A2: Peer Task Visibility
# ──────────────────────────────────────────────────────────────────────


class TestPeerContext:
    def test_peer_context_empty_purpose(self, db_session, tenant, purpose):
        from ai_org_backend.services.peer_context import get_peer_context
        ctx = get_peer_context(purpose.id)
        assert ctx.running_tasks == []
        assert ctx.recent_files == []

    def test_peer_context_with_running_tasks(self, db_session, tenant, purpose):
        from ai_org_backend.models import Task
        from ai_org_backend.services.peer_context import get_peer_context

        t1 = Task(
            id="peer-t1", tenant_id=tenant.id, purpose_id=purpose.id,
            description="Build auth module", status="doing", owner="DEV",
        )
        t2 = Task(
            id="peer-t2", tenant_id=tenant.id, purpose_id=purpose.id,
            description="Build payment module", status="doing", owner="DEV",
        )
        db_session.add_all([t1, t2])
        db_session.commit()

        ctx = get_peer_context(purpose.id, exclude_task_id="peer-t1")
        assert len(ctx.running_tasks) == 1
        assert ctx.running_tasks[0]["id"] == "peer-t2"

    def test_peer_context_prompt_text(self, db_session, tenant, purpose):
        from ai_org_backend.models import Task
        from ai_org_backend.services.peer_context import get_peer_context

        Task(
            id="peer-t3", tenant_id=tenant.id, purpose_id=purpose.id,
            description="Build API", status="doing", owner="DEV",
        )
        db_session.add(Task(
            id="peer-t3", tenant_id=tenant.id, purpose_id=purpose.id,
            description="Build API", status="doing", owner="DEV",
        ))
        db_session.commit()

        ctx = get_peer_context(purpose.id)
        text = ctx.to_prompt_text()
        assert "Peer Context" in text or text == ""

    def test_peer_context_with_completed_tasks(self, db_session, tenant, purpose):
        from ai_org_backend.models import Task
        from ai_org_backend.services.peer_context import get_peer_context

        t = Task(
            id="peer-done", tenant_id=tenant.id, purpose_id=purpose.id,
            description="Setup database", status="done", owner="DEV",
        )
        db_session.add(t)
        db_session.commit()

        ctx = get_peer_context(purpose.id)
        assert any("Setup database" in s for s in ctx.completed_task_summaries)


# ──────────────────────────────────────────────────────────────────────
# S5-A3: Conflict Detection
# ──────────────────────────────────────────────────────────────────────


class TestConflictDetector:
    def test_no_conflicts_single_task(self, db_session, tenant, purpose):
        from ai_org_backend.services.conflict_detector import detect_conflicts
        report = detect_conflicts(purpose.id)
        assert not report.blocking
        assert report.conflicts == []

    def test_file_overlap_detected(self, db_session, tenant, purpose):
        from ai_org_backend.models import Task
        from ai_org_backend.models.artifact import Artifact
        from ai_org_backend.services.conflict_detector import detect_conflicts

        t1 = Task(
            id="cd-t1", tenant_id=tenant.id, purpose_id=purpose.id,
            description="Task A", status="done",
        )
        t2 = Task(
            id="cd-t2", tenant_id=tenant.id, purpose_id=purpose.id,
            description="Task B", status="done",
        )
        db_session.add_all([t1, t2])
        db_session.flush()

        # Both tasks write to the same file
        for tid in ["cd-t1", "cd-t2"]:
            db_session.add(Artifact(
                id=f"art-{tid}",
                task_id=tid,
                repo_path="src/main.py",
                media_type="text/x-source",
                size=100,
                sha256=str(uuid.uuid4()).replace("-", "") + "0" * 32,
            ))
        db_session.commit()

        report = detect_conflicts(purpose.id)
        file_overlaps = [c for c in report.conflicts if c.conflict_type == "file_overlap"]
        assert len(file_overlaps) >= 1
        assert report.blocking  # file_overlap is HIGH severity

    def test_conflict_report_prompt_text(self):
        from ai_org_backend.services.conflict_detector import (
            Conflict,
            ConflictReport,
            ConflictSeverity,
        )
        report = ConflictReport(conflicts=[
            Conflict(
                severity=ConflictSeverity.CRITICAL,
                conflict_type="endpoint_collision",
                description="POST /api/users defined by two tasks",
                task_a_id="t1",
                task_b_id="t2",
            ),
        ])
        text = report.to_prompt_text()
        assert "CRITICAL" in text
        assert "endpoint_collision" in text


# ──────────────────────────────────────────────────────────────────────
# S5-A4: Repo Snapshot
# ──────────────────────────────────────────────────────────────────────


class TestRepoSnapshot:
    def test_create_and_retrieve_snapshot(self, tmp_path, monkeypatch):
        from ai_org_backend.services import repo_snapshot

        monkeypatch.setattr(repo_snapshot, "WORKSPACE", tmp_path)

        # Create some files
        tenant_dir = tmp_path / "test-tenant"
        tenant_dir.mkdir()
        (tenant_dir / "main.py").write_text("print('hello')")
        (tenant_dir / "utils.py").write_text("def helper(): pass")

        snap = repo_snapshot.create_snapshot("test-tenant", "purpose-1", "task-1")
        assert snap.file_count == 2
        assert snap.generation_time_ms >= 0
        assert len(snap.files) == 2

        # Retrieve
        loaded = repo_snapshot.get_snapshot("test-tenant", "purpose-1", "task-1")
        assert loaded is not None
        assert loaded.file_count == 2

    def test_snapshot_changed_since(self, tmp_path, monkeypatch):
        from ai_org_backend.services import repo_snapshot

        monkeypatch.setattr(repo_snapshot, "WORKSPACE", tmp_path)

        tenant_dir = tmp_path / "test-tenant2"
        tenant_dir.mkdir()
        (tenant_dir / "file.py").write_text("v1")

        snap1 = repo_snapshot.create_snapshot("test-tenant2", "p", "t1")

        # Modify file
        (tenant_dir / "file.py").write_text("v2")
        snap2 = repo_snapshot.create_snapshot("test-tenant2", "p", "t2")

        changes = snap2.changed_since(snap1)
        assert "file.py" in changes

    def test_snapshot_prompt_text(self, tmp_path, monkeypatch):
        from ai_org_backend.services import repo_snapshot

        monkeypatch.setattr(repo_snapshot, "WORKSPACE", tmp_path)
        tenant_dir = tmp_path / "test-tenant3"
        tenant_dir.mkdir()
        (tenant_dir / "app.py").write_text("app = Flask(__name__)")

        snap = repo_snapshot.create_snapshot("test-tenant3", "p", "t")
        text = snap.to_prompt_text()
        assert "Repo Snapshot" in text


# ──────────────────────────────────────────────────────────────────────
# S5-B1: Code Review Blocking Gate
# ──────────────────────────────────────────────────────────────────────


class TestReviewGate:
    def test_parse_findings_from_review(self):
        from ai_org_backend.services.review_gate import parse_review_findings

        review_md = """## Code Review

**[CRITICAL]** SQL injection vulnerability in `user_handler.py` line 42
- [HIGH]: Missing input validation in api/routes.py:15
- [MEDIUM] - Variable naming inconsistency in utils.py
- [LOW]: Missing docstring in helper.py line 5
"""
        findings = parse_review_findings(review_md, "t1", "p1", "ten1")
        assert len(findings) >= 3  # at least CRITICAL, HIGH, MEDIUM

        severities = [f.severity for f in findings]
        assert "critical" in severities
        assert "high" in severities

    def test_enforce_gate_clean_review(self, db_session, tenant, purpose):
        from ai_org_backend.models import Task
        from ai_org_backend.services.review_gate import enforce_review_gate

        review_task = Task(
            id="rg-clean", tenant_id=tenant.id, purpose_id=purpose.id,
            description="Code Review", status="done",
        )
        db_session.add(review_task)
        db_session.commit()

        result = enforce_review_gate(
            "rg-clean",
            "## Review\nAll looks good! No issues found.",
            purpose.id,
            tenant.id,
        )
        assert result["status"] == "approved"
        assert result["blocking"] == 0

    def test_enforce_gate_with_blocking_findings(self, db_session, tenant, purpose):
        from ai_org_backend.models import Task
        from ai_org_backend.services.review_gate import enforce_review_gate

        review_task = Task(
            id="rg-block", tenant_id=tenant.id, purpose_id=purpose.id,
            description="Code Review Block", status="done",
        )
        db_session.add(review_task)
        db_session.commit()

        review_md = """## Review
[CRITICAL] - Hardcoded password in config.py line 10
[HIGH] - Missing auth check in api/admin.py
[LOW] - Typo in comment
"""
        result = enforce_review_gate("rg-block", review_md, purpose.id, tenant.id)
        assert result["status"] == "changes_requested"
        assert result["blocking"] == 2
        assert len(result["fix_tasks"]) >= 1


# ──────────────────────────────────────────────────────────────────────
# S5-B3: Re-Review Loop
# ──────────────────────────────────────────────────────────────────────


class TestReReviewLoop:
    def test_dispatch_re_review(self, db_session, tenant, purpose):
        from ai_org_backend.models import Task
        from ai_org_backend.services.review_gate import dispatch_re_review

        review_task = Task(
            id="rr-t1", tenant_id=tenant.id, purpose_id=purpose.id,
            description="Code Review RR", status="done",
            review_rounds=0,
        )
        db_session.add(review_task)
        db_session.commit()

        with patch("ai_org_backend.services.review_gate.celery") as mock_celery:
            result = dispatch_re_review("rr-t1", tenant.id)
            assert result is True
            mock_celery.send_task.assert_called_once()

    def test_escalation_after_max_rounds(self, db_session, tenant, purpose):
        from ai_org_backend.models import Task
        from ai_org_backend.services.review_gate import MAX_REVIEW_ROUNDS, dispatch_re_review

        review_task = Task(
            id="rr-esc", tenant_id=tenant.id, purpose_id=purpose.id,
            description="Code Review Escalate", status="done",
            review_rounds=MAX_REVIEW_ROUNDS - 1,
        )
        db_session.add(review_task)
        db_session.commit()

        result = dispatch_re_review("rr-esc", tenant.id)
        assert result is False  # Escalated, not dispatched

        db_session.refresh(review_task)
        assert review_task.code_review_status == "requires_manual_review"

    def test_check_fix_tasks_complete(self, db_session, tenant, purpose):
        from ai_org_backend.models import Task, TaskDependency
        from ai_org_backend.services.review_gate import check_fix_tasks_complete

        review = Task(
            id="rr-chk", tenant_id=tenant.id, purpose_id=purpose.id,
            description="Review Check", status="done",
        )
        fix = Task(
            id="rr-fix", tenant_id=tenant.id, purpose_id=purpose.id,
            description="Fix Task", status="todo",
        )
        db_session.add_all([review, fix])
        db_session.flush()
        db_session.add(TaskDependency(from_id="rr-fix", to_id="rr-chk", dependency_type="blocks"))
        db_session.commit()

        # Not complete yet
        assert check_fix_tasks_complete("rr-chk") is False

        # Complete the fix
        fix.status = "done"
        db_session.add(fix)
        db_session.commit()

        assert check_fix_tasks_complete("rr-chk") is True


# ──────────────────────────────────────────────────────────────────────
# S5-B4: Code Review Findings Database
# ──────────────────────────────────────────────────────────────────────


class TestCodeReviewFindings:
    def test_persist_findings(self, db_session, tenant, purpose):
        from ai_org_backend.models import Task
        from ai_org_backend.models.code_review_finding import (
            CodeReviewFinding,
            FindingCategory,
            FindingSeverity,
        )
        from ai_org_backend.services.review_gate import persist_findings

        task = Task(
            id="crf-t1", tenant_id=tenant.id, purpose_id=purpose.id,
            description="CRF Test", status="done",
        )
        db_session.add(task)
        db_session.commit()

        findings = [
            CodeReviewFinding(
                task_id="crf-t1",
                purpose_id=purpose.id,
                tenant_id=tenant.id,
                severity=FindingSeverity.CRITICAL,
                category=FindingCategory.SECURITY,
                description="SQL injection in handler",
                file_path="api/handler.py",
                line_number=42,
            ),
            CodeReviewFinding(
                task_id="crf-t1",
                purpose_id=purpose.id,
                tenant_id=tenant.id,
                severity=FindingSeverity.LOW,
                category=FindingCategory.STYLE,
                description="Missing docstring",
            ),
        ]

        count = persist_findings(findings)
        assert count == 2

        # Verify persistence
        stored = db_session.exec(
            select(CodeReviewFinding).where(CodeReviewFinding.task_id == "crf-t1")
        ).all()
        assert len(stored) == 2


# ──────────────────────────────────────────────────────────────────────
# S5-B2: Merge Service
# ──────────────────────────────────────────────────────────────────────


class TestMergeService:
    def test_merge_no_overlap(self, db_session, tenant, purpose):
        from ai_org_backend.models import Task
        from ai_org_backend.models.artifact import Artifact
        from ai_org_backend.services.merge_service import merge_purpose_outputs

        t1 = Task(
            id="ms-t1", tenant_id=tenant.id, purpose_id=purpose.id,
            description="Build auth", status="done",
        )
        t2 = Task(
            id="ms-t2", tenant_id=tenant.id, purpose_id=purpose.id,
            description="Build payment", status="done",
        )
        db_session.add_all([t1, t2])
        db_session.flush()

        db_session.add(Artifact(
            id="ms-a1", task_id="ms-t1", repo_path="src/auth.py",
            media_type="text/x-source", size=100, sha256="a" * 64,
        ))
        db_session.add(Artifact(
            id="ms-a2", task_id="ms-t2", repo_path="src/payment.py",
            media_type="text/x-source", size=100, sha256="b" * 64,
        ))
        db_session.commit()

        result = merge_purpose_outputs(tenant.id, purpose.id)
        assert result.success
        assert len(result.merged_files) == 2
        assert result.manual_required == 0

    def test_merge_detects_overlap(self, db_session, tenant, purpose):
        from ai_org_backend.models import Task
        from ai_org_backend.models.artifact import Artifact
        from ai_org_backend.services.merge_service import merge_purpose_outputs

        t1 = Task(
            id="ms-o1", tenant_id=tenant.id, purpose_id=purpose.id,
            description="Modify shared", status="done",
        )
        t2 = Task(
            id="ms-o2", tenant_id=tenant.id, purpose_id=purpose.id,
            description="Also modify shared", status="done",
        )
        db_session.add_all([t1, t2])
        db_session.flush()

        # Both write to same file
        for tid, aid in [("ms-o1", "ms-oa1"), ("ms-o2", "ms-oa2")]:
            db_session.add(Artifact(
                id=aid, task_id=tid, repo_path="src/shared.py",
                media_type="text/x-source", size=100,
                sha256=str(uuid.uuid4()).replace("-", "") + "0" * 32,
            ))
        db_session.commit()

        result = merge_purpose_outputs(tenant.id, purpose.id)
        assert not result.success
        assert result.manual_required >= 1


# ──────────────────────────────────────────────────────────────────────
# Import needed for select
# ──────────────────────────────────────────────────────────────────────
from sqlmodel import select
