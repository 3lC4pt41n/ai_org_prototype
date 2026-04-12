"""Sprint 5 audit tests: Multi-Agent Coordination & Code Review Gates.

Covers:
- S5-A1: Shared Contracts loading + prompt injection
- S5-A2: Peer Task Visibility (peer_context)
- S5-A3: Conflict Detection (file overlap, endpoint, package, class redef)
- S5-A4: Repo Snapshot (create, retrieve, diff)
- S5-B1: Code Review Blocking Gate (enforce_review_gate)
- S5-B2: Smart Merge Service (merge_purpose_outputs)
- S5-B3: Re-Review Loop (dispatch_re_review, escalation)
- S5-B4: CodeReviewFinding persistence
- Template integration: dev.j2, code_review.j2 include S5 variables
"""

from __future__ import annotations

# Python 3.10 compatibility shim – must be before any model imports
import enum
if not hasattr(enum, "StrEnum"):
    try:
        from strenum import StrEnum
        enum.StrEnum = StrEnum
    except ImportError:
        pass

import json
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select


# ---------------------------------------------------------------------------
# Session-scoped engine with all models imported before create_all
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def s5_engine():
    """Shared in-memory SQLite engine for all Sprint 5 tests."""
    eng = create_engine(
        "sqlite://",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Import ALL models so metadata.create_all() sees every table
    import ai_org_backend.models  # noqa: F401
    import ai_org_backend.models.artifact  # noqa: F401
    import ai_org_backend.models.code_review_finding  # noqa: F401
    import ai_org_backend.models.file_reservation  # noqa: F401
    import ai_org_backend.models.merge_conflict  # noqa: F401

    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture(autouse=True)
def _patch_engine(s5_engine, monkeypatch):
    """Monkeypatch engine everywhere Sprint 5 services import it."""
    import ai_org_backend.db as db_mod
    import ai_org_backend.services.peer_context as pc_mod
    import ai_org_backend.services.conflict_detector as cd_mod
    import ai_org_backend.services.review_gate as rg_mod
    import ai_org_backend.services.merge_service as ms_mod
    import ai_org_backend.services.file_reservation as fr_mod

    monkeypatch.setattr(db_mod, "engine", s5_engine)
    monkeypatch.setattr(pc_mod, "engine", s5_engine)
    monkeypatch.setattr(cd_mod, "engine", s5_engine)
    monkeypatch.setattr(rg_mod, "engine", s5_engine)
    monkeypatch.setattr(ms_mod, "engine", s5_engine)
    monkeypatch.setattr(fr_mod, "engine", s5_engine)

    # Also patch SessionLocal where used
    from sqlmodel import Session as _S
    _sl = lambda: _S(s5_engine)  # noqa: E731
    if hasattr(db_mod, "SessionLocal"):
        monkeypatch.setattr(db_mod, "SessionLocal", _sl)


@pytest.fixture
def db(s5_engine):
    with Session(s5_engine) as session:
        yield session


@pytest.fixture
def tenant(db):
    from ai_org_backend.models import Tenant
    tid = f"s5-{uuid.uuid4().hex[:6]}"
    t = Tenant(id=tid, name="S5 Tenant", email=f"{tid}@test.com", hashed_password="x")
    db.add(t)
    db.commit()
    return t


@pytest.fixture
def purpose(db, tenant):
    from ai_org_backend.models import Purpose
    p = Purpose(
        id=str(uuid.uuid4())[:8],
        tenant_id=tenant.id,
        name="S5 Purpose",
        mode="auto",
    )
    db.add(p)
    db.commit()
    return p


def _find_prompts_dir() -> Path:
    """Find the prompts/ directory (at repo root, one level above backend/)."""
    here = Path(__file__).resolve().parent  # tests/
    for parent in [here, *here.parents]:
        candidate = parent / "prompts"
        if candidate.is_dir() and (candidate / "dev.j2").exists():
            return candidate
    raise FileNotFoundError("prompts/ dir not found")


# ══════════════════════════════════════════════════════════════════════
# S5-A1: Shared Contracts
# ══════════════════════════════════════════════════════════════════════

class TestSharedContracts:
    """S5-A1: shared_contracts.txt loading + caching."""

    def test_load_returns_string(self):
        from ai_org_backend.services.shared_contracts import load_shared_contracts
        load_shared_contracts.cache_clear()
        text = load_shared_contracts()
        assert isinstance(text, str)

    def test_lru_cache_works(self):
        from ai_org_backend.services.shared_contracts import load_shared_contracts
        load_shared_contracts.cache_clear()
        a = load_shared_contracts()
        b = load_shared_contracts()
        assert a is b  # same object — cached

    def test_missing_file_returns_empty(self, monkeypatch):
        from ai_org_backend.services import shared_contracts as sc_mod
        monkeypatch.setattr(
            sc_mod, "_find_contracts_file",
            lambda: (_ for _ in ()).throw(FileNotFoundError("nope")),
        )
        sc_mod.load_shared_contracts.cache_clear()
        assert sc_mod.load_shared_contracts() == ""

    def test_dev_j2_includes_shared_contracts_block(self):
        tmpl = (_find_prompts_dir() / "dev.j2").read_text()
        assert "shared_contracts" in tmpl
        assert "MANDATORY" in tmpl

    def test_code_review_j2_includes_shared_contracts_block(self):
        tmpl = (_find_prompts_dir() / "code_review.j2").read_text()
        assert "shared_contracts" in tmpl
        assert "CRITICAL" in tmpl


# ══════════════════════════════════════════════════════════════════════
# S5-A2: Peer Task Visibility
# ══════════════════════════════════════════════════════════════════════

class TestPeerContext:
    """S5-A2: Peer context for multi-agent visibility."""

    def test_empty_purpose_returns_blank(self, db, tenant, purpose):
        from ai_org_backend.services.peer_context import get_peer_context
        ctx = get_peer_context(purpose.id)
        assert ctx.running_tasks == []
        assert ctx.recent_files == []

    def test_running_peers_visible(self, db, tenant, purpose):
        from ai_org_backend.models import Task
        from ai_org_backend.services.peer_context import get_peer_context

        t1 = Task(id="pc-a", tenant_id=tenant.id, purpose_id=purpose.id,
                   description="Auth module", status="doing", owner="DEV")
        t2 = Task(id="pc-b", tenant_id=tenant.id, purpose_id=purpose.id,
                   description="Payment module", status="doing", owner="DEV")
        db.add_all([t1, t2])
        db.commit()

        ctx = get_peer_context(purpose.id, exclude_task_id="pc-a")
        ids = [t["id"] for t in ctx.running_tasks]
        assert "pc-b" in ids
        assert "pc-a" not in ids

    def test_prompt_text_contains_peer_section(self, db, tenant, purpose):
        from ai_org_backend.models import Task
        from ai_org_backend.services.peer_context import get_peer_context

        db.add(Task(id="pc-c", tenant_id=tenant.id, purpose_id=purpose.id,
                     description="DB setup", status="doing", owner="DEV"))
        db.commit()

        ctx = get_peer_context(purpose.id)
        text = ctx.to_prompt_text()
        assert "Peer Context" in text

    def test_dev_j2_includes_peer_context_block(self):
        tmpl = (_find_prompts_dir() / "dev.j2").read_text()
        assert "peer_context" in tmpl

    def test_dev_j2_includes_conflict_warnings_block(self):
        tmpl = (_find_prompts_dir() / "dev.j2").read_text()
        assert "conflict_warnings" in tmpl


# ══════════════════════════════════════════════════════════════════════
# S5-A3: Conflict Detection
# ══════════════════════════════════════════════════════════════════════

class TestConflictDetector:
    """S5-A3: Multi-type conflict detection."""

    def test_no_conflicts_single_task(self, db, tenant, purpose):
        from ai_org_backend.services.conflict_detector import detect_conflicts
        report = detect_conflicts(purpose.id)
        assert not report.blocking
        assert report.conflicts == []

    def test_file_overlap_detected(self, db, tenant, purpose):
        from ai_org_backend.models import Task
        from ai_org_backend.models.artifact import Artifact
        from ai_org_backend.services.conflict_detector import detect_conflicts

        for i, tid in enumerate(["cd-x1", "cd-x2"]):
            db.add(Task(id=tid, tenant_id=tenant.id, purpose_id=purpose.id,
                        description=f"Task {i}", status="done"))
        db.flush()
        for tid in ["cd-x1", "cd-x2"]:
            db.add(Artifact(
                id=f"art-{tid}", task_id=tid,
                repo_path="src/overlap.py",
                media_type="text/x-source", size=100,
                sha256=uuid.uuid4().hex + "0" * 32,
            ))
        db.commit()

        report = detect_conflicts(purpose.id)
        overlaps = [c for c in report.conflicts if c.conflict_type == "file_overlap"]
        assert len(overlaps) >= 1
        assert report.blocking

    def test_conflict_severity_blocking_property(self):
        from ai_org_backend.services.conflict_detector import (
            Conflict, ConflictReport, ConflictSeverity,
        )
        report = ConflictReport(conflicts=[
            Conflict(
                severity=ConflictSeverity.CRITICAL,
                conflict_type="endpoint_collision",
                description="POST /api/users clash",
                task_a_id="t1", task_b_id="t2",
            ),
        ])
        assert report.blocking
        assert report.has_critical is False  # has_critical set externally
        text = report.to_prompt_text()
        assert "CRITICAL" in text

    def test_conflict_report_empty_has_no_text(self):
        from ai_org_backend.services.conflict_detector import ConflictReport
        assert ConflictReport().to_prompt_text() == ""


# ══════════════════════════════════════════════════════════════════════
# S5-A4: Repo Snapshot
# ══════════════════════════════════════════════════════════════════════

class TestRepoSnapshot:
    """S5-A4: Immutable workspace snapshots."""

    def test_create_snapshot(self, tmp_path, monkeypatch):
        from ai_org_backend.services import repo_snapshot as rs_mod
        monkeypatch.setattr(rs_mod, "WORKSPACE", tmp_path)

        tenant_dir = tmp_path / "snap-ten"
        tenant_dir.mkdir()
        (tenant_dir / "main.py").write_text("print('hi')")
        (tenant_dir / "utils.py").write_text("def f(): pass")

        snap = rs_mod.create_snapshot("snap-ten", "p1", "t1")
        assert snap.file_count == 2
        assert len(snap.files) == 2
        assert snap.generation_time_ms >= 0

    def test_retrieve_snapshot(self, tmp_path, monkeypatch):
        from ai_org_backend.services import repo_snapshot as rs_mod
        monkeypatch.setattr(rs_mod, "WORKSPACE", tmp_path)

        tenant_dir = tmp_path / "snap-ten2"
        tenant_dir.mkdir()
        (tenant_dir / "app.py").write_text("x = 1")

        rs_mod.create_snapshot("snap-ten2", "p", "t")
        loaded = rs_mod.get_snapshot("snap-ten2", "p", "t")
        assert loaded is not None
        assert loaded.file_count == 1

    def test_changed_since(self, tmp_path, monkeypatch):
        from ai_org_backend.services import repo_snapshot as rs_mod
        monkeypatch.setattr(rs_mod, "WORKSPACE", tmp_path)

        d = tmp_path / "snap-ten3"
        d.mkdir()
        (d / "f.py").write_text("v1")
        snap1 = rs_mod.create_snapshot("snap-ten3", "p", "t1")

        (d / "f.py").write_text("v2")
        snap2 = rs_mod.create_snapshot("snap-ten3", "p", "t2")

        changes = snap2.changed_since(snap1)
        assert "f.py" in changes

    def test_max_files_safety_limit(self):
        from ai_org_backend.services.repo_snapshot import MAX_FILES
        assert MAX_FILES == 5000

    def test_prompt_text(self, tmp_path, monkeypatch):
        from ai_org_backend.services import repo_snapshot as rs_mod
        monkeypatch.setattr(rs_mod, "WORKSPACE", tmp_path)
        d = tmp_path / "snap-ten4"
        d.mkdir()
        (d / "a.py").write_text("1")
        snap = rs_mod.create_snapshot("snap-ten4", "p", "t")
        assert "Repo Snapshot" in snap.to_prompt_text()


# ══════════════════════════════════════════════════════════════════════
# S5-B1: Code Review Blocking Gate
# ══════════════════════════════════════════════════════════════════════

class TestReviewGate:
    """S5-B1: Code review as enforcement gate."""

    def test_parse_severity_tagged_findings(self):
        from ai_org_backend.services.review_gate import parse_review_findings

        md = """## Review
[CRITICAL] SQL injection in `handler.py` line 42
**[HIGH]**: Missing auth check in api/routes.py:15
- [MEDIUM] - Naming issue in utils.py
- [LOW]: Missing docstring in helper.py line 5
"""
        findings = parse_review_findings(md, "rt1", "p1", "ten1")
        severities = [f.severity for f in findings]
        assert "critical" in severities
        assert "high" in severities
        assert len(findings) == 4

    def test_finding_category_classification(self):
        from ai_org_backend.services.review_gate import _classify_category
        assert _classify_category("SQL injection vulnerability") == "security"
        assert _classify_category("slow database query") == "performance"
        assert _classify_category("missing test coverage") == "testing"

    def test_enforce_gate_approved(self, db, tenant, purpose):
        from ai_org_backend.models import Task
        from ai_org_backend.services.review_gate import enforce_review_gate

        db.add(Task(id="rg-ok", tenant_id=tenant.id, purpose_id=purpose.id,
                     description="Review OK", status="done"))
        db.commit()

        result = enforce_review_gate(
            "rg-ok", "## Review\nAll looks good!", purpose.id, tenant.id,
        )
        assert result["status"] == "approved"
        assert result["blocking"] == 0

    def test_enforce_gate_creates_fix_tasks(self, db, tenant, purpose):
        from ai_org_backend.models import Task
        from ai_org_backend.services.review_gate import enforce_review_gate

        db.add(Task(id="rg-blk", tenant_id=tenant.id, purpose_id=purpose.id,
                     description="Review Block", status="done"))
        db.commit()

        md = """[CRITICAL] - Hardcoded secret in config.py line 10
[HIGH] - Missing auth in api/admin.py
[LOW] - Typo in comment"""
        result = enforce_review_gate("rg-blk", md, purpose.id, tenant.id)
        assert result["status"] == "changes_requested"
        assert result["blocking"] == 2
        assert len(result["fix_tasks"]) >= 1


# ══════════════════════════════════════════════════════════════════════
# S5-B3: Re-Review Loop
# ══════════════════════════════════════════════════════════════════════

class TestReReviewLoop:
    """S5-B3: Re-review dispatch + escalation."""

    def test_dispatch_re_review_success(self, db, tenant, purpose):
        from ai_org_backend.models import Task
        from ai_org_backend.services.review_gate import dispatch_re_review

        db.add(Task(id="rr-ok", tenant_id=tenant.id, purpose_id=purpose.id,
                     description="Re-Review OK", status="done", review_rounds=0))
        db.commit()

        with patch("ai_org_backend.tasks.celery_app.celery") as mock_cel:
            assert dispatch_re_review("rr-ok", tenant.id) is True
            mock_cel.send_task.assert_called_once()

    def test_escalation_after_max_rounds(self, db, tenant, purpose):
        from ai_org_backend.models import Task
        from ai_org_backend.services.review_gate import MAX_REVIEW_ROUNDS, dispatch_re_review

        db.add(Task(id="rr-esc", tenant_id=tenant.id, purpose_id=purpose.id,
                     description="Escalate", status="done",
                     review_rounds=MAX_REVIEW_ROUNDS - 1))
        db.commit()

        result = dispatch_re_review("rr-esc", tenant.id)
        assert result is False

        db.expire_all()
        from ai_org_backend.models import Task as T
        task = db.get(T, "rr-esc")
        assert task.code_review_status == "requires_manual_review"

    def test_max_review_rounds_constant(self):
        from ai_org_backend.services.review_gate import MAX_REVIEW_ROUNDS
        assert MAX_REVIEW_ROUNDS == 3

    def test_check_fix_tasks_complete(self, db, tenant, purpose):
        from ai_org_backend.models import Task, TaskDependency
        from ai_org_backend.services.review_gate import check_fix_tasks_complete

        db.add(Task(id="rr-rv", tenant_id=tenant.id, purpose_id=purpose.id,
                     description="Review", status="done"))
        db.add(Task(id="rr-fx", tenant_id=tenant.id, purpose_id=purpose.id,
                     description="Fix", status="todo"))
        db.flush()
        db.add(TaskDependency(from_id="rr-fx", to_id="rr-rv", dependency_type="blocks"))
        db.commit()

        assert check_fix_tasks_complete("rr-rv") is False

        fix = db.get(Task, "rr-fx")
        fix.status = "done"
        db.add(fix)
        db.commit()

        assert check_fix_tasks_complete("rr-rv") is True


# ══════════════════════════════════════════════════════════════════════
# S5-B4: CodeReviewFinding Persistence
# ══════════════════════════════════════════════════════════════════════

class TestCodeReviewFindings:
    """S5-B4: Structured finding storage."""

    def test_persist_findings(self, db, tenant, purpose):
        from ai_org_backend.models import Task
        from ai_org_backend.models.code_review_finding import (
            CodeReviewFinding, FindingCategory, FindingSeverity,
        )
        from ai_org_backend.services.review_gate import persist_findings

        db.add(Task(id="crf-1", tenant_id=tenant.id, purpose_id=purpose.id,
                     description="CRF Test", status="done"))
        db.commit()

        findings = [
            CodeReviewFinding(
                task_id="crf-1", purpose_id=purpose.id, tenant_id=tenant.id,
                severity=FindingSeverity.CRITICAL, category=FindingCategory.SECURITY,
                description="SQL injection", file_path="handler.py", line_number=42,
            ),
            CodeReviewFinding(
                task_id="crf-1", purpose_id=purpose.id, tenant_id=tenant.id,
                severity=FindingSeverity.LOW, category=FindingCategory.STYLE,
                description="Missing docstring",
            ),
        ]
        count = persist_findings(findings)
        assert count == 2

        stored = db.exec(
            select(CodeReviewFinding).where(CodeReviewFinding.task_id == "crf-1")
        ).all()
        assert len(stored) == 2

    def test_finding_model_fields(self):
        from ai_org_backend.models.code_review_finding import CodeReviewFinding
        f = CodeReviewFinding(
            task_id="t", purpose_id="p", tenant_id="ten",
            severity="high", description="test",
        )
        assert f.fixed is False
        assert f.fix_task_id is None
        assert f.line_number is None


# ══════════════════════════════════════════════════════════════════════
# S5-B2: Smart Merge Service
# ══════════════════════════════════════════════════════════════════════

class TestMergeService:
    """S5-B2: Parallel output merge."""

    def test_no_overlap_succeeds(self, db, tenant, purpose):
        from ai_org_backend.models import Task
        from ai_org_backend.models.artifact import Artifact
        from ai_org_backend.services.merge_service import merge_purpose_outputs

        for i, tid in enumerate(["mg-a", "mg-b"]):
            db.add(Task(id=tid, tenant_id=tenant.id, purpose_id=purpose.id,
                        description=f"Build {i}", status="done"))
        db.flush()
        db.add(Artifact(id="mg-a1", task_id="mg-a", repo_path="src/auth.py",
                        media_type="text/x-source", size=100, sha256="a" * 64))
        db.add(Artifact(id="mg-b1", task_id="mg-b", repo_path="src/pay.py",
                        media_type="text/x-source", size=100, sha256="b" * 64))
        db.commit()

        result = merge_purpose_outputs(tenant.id, purpose.id)
        assert result.success
        assert len(result.merged_files) == 2
        assert result.manual_required == 0

    def test_overlap_creates_conflict(self, db, tenant, purpose):
        from ai_org_backend.models import Task
        from ai_org_backend.models.artifact import Artifact
        from ai_org_backend.services.merge_service import merge_purpose_outputs

        for i, tid in enumerate(["mg-c", "mg-d"]):
            db.add(Task(id=tid, tenant_id=tenant.id, purpose_id=purpose.id,
                        description=f"Overlap {i}", status="done"))
        db.flush()
        for tid, aid in [("mg-c", "mg-c1"), ("mg-d", "mg-d1")]:
            db.add(Artifact(id=aid, task_id=tid, repo_path="src/shared.py",
                            media_type="text/x-source", size=100,
                            sha256=uuid.uuid4().hex + "0" * 32))
        db.commit()

        result = merge_purpose_outputs(tenant.id, purpose.id)
        assert not result.success
        assert result.manual_required >= 1

    def test_merge_conflict_model(self):
        from ai_org_backend.models.merge_conflict import MergeConflict, MergeConflictStatus
        mc = MergeConflict(
            purpose_id="p", tenant_id="t",
            task_a_id="a", task_b_id="b",
            file_path="x.py",
        )
        assert mc.status == MergeConflictStatus.OPEN
        assert mc.resolved_at is None


# ══════════════════════════════════════════════════════════════════════
# Integration: agent_dev.py loads S5 context
# ══════════════════════════════════════════════════════════════════════

class TestAgentDevIntegration:
    """Verify agent_dev.py source includes S5-A1/A2/A3 integration."""

    def test_agent_dev_imports_shared_contracts(self):
        src = (Path(__file__).resolve().parent.parent
               / "ai_org_backend" / "agents" / "agent_dev.py").read_text()
        assert "load_shared_contracts" in src

    def test_agent_dev_imports_peer_context(self):
        src = (Path(__file__).resolve().parent.parent
               / "ai_org_backend" / "agents" / "agent_dev.py").read_text()
        assert "get_peer_context" in src

    def test_agent_dev_imports_conflict_detector(self):
        src = (Path(__file__).resolve().parent.parent
               / "ai_org_backend" / "agents" / "agent_dev.py").read_text()
        assert "detect_conflicts" in src

    def test_code_review_imports_enforce_gate(self):
        src = (Path(__file__).resolve().parent.parent
               / "ai_org_backend" / "agents" / "code_review.py").read_text()
        assert "enforce_review_gate" in src

    def test_task_model_has_review_fields(self):
        src = (Path(__file__).resolve().parent.parent
               / "ai_org_backend" / "models" / "task.py").read_text()
        assert "code_review_status" in src
        assert "review_rounds" in src
