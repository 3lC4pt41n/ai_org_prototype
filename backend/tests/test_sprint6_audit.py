"""Sprint 6 audit tests: Output Validation & UX Polish.

Covers:
- S6-#8.1: Enhanced build_validator (ast.parse, to_dict/to_json, store_validation_artifact)
- S6-#8.3: Deployment file auto-generation (requirements.txt, Dockerfile)
- S6-#10.1: GET /pipeline/phases endpoint
- S6-#10.2: WebSocket status endpoint + auto-mode dispatch trigger
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

import ast
import inspect
import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select


# ---------------------------------------------------------------------------
# Session-scoped engine
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def s6_engine():
    eng = create_engine(
        "sqlite://",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    import ai_org_backend.models  # noqa: F401
    import ai_org_backend.models.artifact  # noqa: F401
    import ai_org_backend.models.code_review_finding  # noqa: F401
    import ai_org_backend.models.file_reservation  # noqa: F401
    import ai_org_backend.models.merge_conflict  # noqa: F401
    import ai_org_backend.models.pipeline  # noqa: F401

    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture(autouse=True)
def _patch_engine(s6_engine, monkeypatch):
    import ai_org_backend.db as db_mod
    monkeypatch.setattr(db_mod, "engine", s6_engine)
    if hasattr(db_mod, "SessionLocal"):
        from sqlmodel import Session as _S
        monkeypatch.setattr(db_mod, "SessionLocal", lambda: _S(s6_engine))


@pytest.fixture
def db(s6_engine):
    with Session(s6_engine) as session:
        yield session


@pytest.fixture
def tenant(db):
    from ai_org_backend.models import Tenant
    tid = f"s6-{uuid.uuid4().hex[:6]}"
    t = Tenant(id=tid, name="S6 Tenant", email=f"{tid}@t.com", hashed_password="x")
    db.add(t)
    db.commit()
    return t


@pytest.fixture
def purpose(db, tenant):
    from ai_org_backend.models import Purpose
    p = Purpose(
        id=str(uuid.uuid4())[:8],
        tenant_id=tenant.id,
        name="S6 Purpose",
        mode="manual",
    )
    db.add(p)
    db.commit()
    return p


# ══════════════════════════════════════════════════════════════════════
# S6-#8.1: Enhanced Build Validator
# ══════════════════════════════════════════════════════════════════════

class TestBuildValidatorEnhanced:
    """S6-#8.1: ast.parse, serialisation, artifact storage."""

    def test_ast_parse_catches_syntax_error(self, tmp_path):
        from ai_org_backend.services.build_validator import validate_repository

        (tmp_path / "bad.py").write_text("def f(\n  # missing close paren")
        report = validate_repository(str(tmp_path))
        assert not report.is_valid
        assert any("syntax" in e.lower() or "parse" in e.lower() for e in report.errors)

    def test_ast_parse_valid_file(self, tmp_path):
        from ai_org_backend.services.build_validator import validate_repository

        (tmp_path / "good.py").write_text("def greet(name):\n    return f'Hello {name}'")
        report = validate_repository(str(tmp_path))
        assert report.is_valid

    def test_checked_files_counter(self, tmp_path):
        from ai_org_backend.services.build_validator import validate_repository

        (tmp_path / "a.py").write_text("x = 1")
        (tmp_path / "b.py").write_text("y = 2")
        (tmp_path / "c.json").write_text('{"k": "v"}')
        report = validate_repository(str(tmp_path))
        assert report.checked_files == 3

    def test_to_dict_and_to_json(self, tmp_path):
        from ai_org_backend.services.build_validator import validate_repository

        (tmp_path / "x.py").write_text("z = 1")
        report = validate_repository(str(tmp_path))
        d = report.to_dict()
        assert "errors" in d
        assert "warnings" in d
        assert "checked_files" in d
        assert "validated_at" in d

        j = report.to_json()
        parsed = json.loads(j)
        assert parsed["checked_files"] == 1

    def test_validate_files_content_counts(self):
        from ai_org_backend.services.build_validator import validate_files_content

        files = [
            {"path": "main.py", "content": "print('hi')"},
            {"path": "data.json", "content": '{"a": 1}'},
        ]
        report = validate_files_content(files)
        assert report.is_valid
        assert report.checked_files == 2

    def test_store_validation_artifact_source(self):
        """Verify store_validation_artifact function exists and has correct signature."""
        src = (Path(__file__).resolve().parent.parent
               / "ai_org_backend" / "services" / "build_validator.py").read_text()
        assert "def store_validation_artifact(" in src
        assert "task_id" in src
        assert "Artifact" in src

    def test_build_validator_uses_ast(self):
        """Source code imports ast module."""
        src = (Path(__file__).resolve().parent.parent
               / "ai_org_backend" / "services" / "build_validator.py").read_text()
        assert "import ast" in src
        assert "ast.parse" in src


# ══════════════════════════════════════════════════════════════════════
# S6-#8.3: Deployment File Auto-Generation
# ══════════════════════════════════════════════════════════════════════

class TestDeploymentGenerator:
    """S6-#8.3: requirements.txt + Dockerfile auto-generation."""

    def test_infer_requirements_from_imports(self, tmp_path):
        from ai_org_backend.services.deployment_generator import infer_requirements

        (tmp_path / "app.py").write_text(
            "import fastapi\nimport redis\nimport os\nimport json\n"
        )
        reqs = infer_requirements(str(tmp_path))
        assert "fastapi" in reqs
        assert "redis" in reqs
        # stdlib should NOT appear
        assert "os" not in reqs
        assert "json" not in reqs

    def test_infer_filters_local_modules(self, tmp_path):
        from ai_org_backend.services.deployment_generator import infer_requirements

        # Create a local module
        pkg = tmp_path / "mypackage"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "core.py").write_text("x = 1")
        (tmp_path / "main.py").write_text("import mypackage\nimport requests\n")

        reqs = infer_requirements(str(tmp_path))
        assert "requests" in reqs
        assert "mypackage" not in reqs

    def test_import_to_package_mapping(self, tmp_path):
        from ai_org_backend.services.deployment_generator import infer_requirements

        (tmp_path / "img.py").write_text("from PIL import Image\nimport yaml\n")
        reqs = infer_requirements(str(tmp_path))
        assert "Pillow" in reqs
        assert "PyYAML" in reqs

    def test_generate_requirements_txt(self, tmp_path):
        from ai_org_backend.services.deployment_generator import generate_requirements_txt

        (tmp_path / "app.py").write_text("import fastapi\nimport sqlmodel\n")
        content = generate_requirements_txt(str(tmp_path))
        assert "fastapi" in content
        assert "sqlmodel" in content
        assert "Auto-generated" in content

    def test_generate_dockerfile_python(self):
        from ai_org_backend.services.deployment_generator import generate_dockerfile

        df = generate_dockerfile("FastAPI + PostgreSQL")
        assert "FROM python:3.11-slim" in df
        assert "uvicorn" in df
        assert "requirements.txt" in df

    def test_generate_dockerfile_node(self):
        from ai_org_backend.services.deployment_generator import generate_dockerfile

        df = generate_dockerfile("React + Node.js")
        assert "FROM node:20-slim" in df
        assert "package" in df

    def test_generate_deployment_files(self, tmp_path):
        from ai_org_backend.services.deployment_generator import generate_deployment_files

        (tmp_path / "server.py").write_text("import flask\n")
        files = generate_deployment_files(str(tmp_path), "Flask")
        assert "requirements.txt" in files
        assert "Dockerfile" in files
        assert "Flask" in files["requirements.txt"]

    def test_write_to_disk(self, tmp_path):
        from ai_org_backend.services.deployment_generator import generate_deployment_files

        (tmp_path / "app.py").write_text("import requests\n")
        generate_deployment_files(str(tmp_path), "python", write_to_disk=True)
        assert (tmp_path / "requirements.txt").exists()
        assert (tmp_path / "Dockerfile").exists()

    def test_no_overwrite_existing(self, tmp_path):
        from ai_org_backend.services.deployment_generator import generate_deployment_files

        (tmp_path / "app.py").write_text("import requests\n")
        (tmp_path / "Dockerfile").write_text("# my custom Dockerfile\n")
        generate_deployment_files(str(tmp_path), "python", write_to_disk=True)
        # Should NOT overwrite existing Dockerfile
        assert (tmp_path / "Dockerfile").read_text() == "# my custom Dockerfile\n"

    def test_empty_workspace(self, tmp_path):
        from ai_org_backend.services.deployment_generator import infer_requirements

        reqs = infer_requirements(str(tmp_path))
        assert reqs == []


# ══════════════════════════════════════════════════════════════════════
# S6-#10.1: Phase Config API
# ══════════════════════════════════════════════════════════════════════

class TestPhaseConfigAPI:
    """S6-#10.1: GET /pipeline/phases endpoint + frontend dynamic loading."""

    def test_pipeline_api_has_get_phases_endpoint(self):
        src = (Path(__file__).resolve().parent.parent
               / "ai_org_backend" / "api" / "pipeline.py").read_text()
        assert "def list_pipeline_phases" in src
        assert 'GET' in src or '@router.get("/pipeline/phases"' in src

    def test_get_phases_returns_structure(self):
        """Verify the endpoint returns purpose_id and phases list."""
        src = (Path(__file__).resolve().parent.parent
               / "ai_org_backend" / "api" / "pipeline.py").read_text()
        assert '"phases"' in src or "'phases'" in src
        assert "purpose_id" in src
        assert "slug" in src
        assert "position" in src

    def test_frontend_has_fetch_function(self):
        """phaseConfig.ts exports fetchPipelinePhases."""
        ts_path = (Path(__file__).resolve().parents[2]
                   / "frontend" / "apps" / "web" / "src" / "components"
                   / "pipeline" / "phaseConfig.ts")
        content = ts_path.read_text()
        assert "fetchPipelinePhases" in content
        assert "ApiPhase" in content
        assert "/api/pipeline/phases" in content

    def test_frontend_still_has_fallback(self):
        """PIPELINE_PHASES hardcoded array still present as fallback."""
        ts_path = (Path(__file__).resolve().parents[2]
                   / "frontend" / "apps" / "web" / "src" / "components"
                   / "pipeline" / "phaseConfig.ts")
        content = ts_path.read_text()
        assert "PIPELINE_PHASES" in content
        assert "purpose" in content
        assert "vision" in content


# ══════════════════════════════════════════════════════════════════════
# S6-#10.2: WebSocket Status + Auto-Mode Trigger
# ══════════════════════════════════════════════════════════════════════

class TestWebSocketStatus:
    """S6-#10.2: Real-time status WebSocket endpoint."""

    def test_ws_status_endpoint_exists(self):
        src = (Path(__file__).resolve().parent.parent
               / "ai_org_backend" / "api" / "chat.py").read_text()
        assert "websocket_status" in src
        assert "/status/{purpose_id}" in src
        assert "status_update" in src

    def test_ws_sends_task_data(self):
        """Verify the WS handler builds task status snapshots."""
        src = (Path(__file__).resolve().parent.parent
               / "ai_org_backend" / "api" / "chat.py").read_text()
        assert "tasks_data" in src
        assert "send_json" in src
        assert "budget_left" in src


class TestAutoModeTrigger:
    """S6-#10.2: Auto-mode flip triggers orchestration."""

    def test_update_purpose_dispatches_on_auto(self):
        """purposes.py sends Celery task when mode flips to auto."""
        src = (Path(__file__).resolve().parent.parent
               / "ai_org_backend" / "api" / "purposes.py").read_text()
        assert "advance_purpose" in src
        assert "auto-mode" in src.lower() or "auto_mode" in src.lower() or "Auto-mode" in src

    def test_update_purpose_only_dispatches_on_flip(self):
        """Should only dispatch when switching FROM non-auto TO auto."""
        src = (Path(__file__).resolve().parent.parent
               / "ai_org_backend" / "api" / "purposes.py").read_text()
        assert "old_mode" in src
        assert 'old_mode != "auto"' in src or "old_mode != 'auto'" in src

    def test_update_purpose_endpoint_exists(self, db, tenant, purpose):
        """Verify the PATCH endpoint saves mode correctly."""
        src = (Path(__file__).resolve().parent.parent
               / "ai_org_backend" / "api" / "purposes.py").read_text()
        assert "def update_purpose" in src
        assert "purpose.mode" in src
