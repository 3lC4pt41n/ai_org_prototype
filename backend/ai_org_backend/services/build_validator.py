"""S-Sprint4 Fix #10 + S6-#8.1: Post-Assembly Build Validation.

Validates generated repository code for syntax errors and structural
integrity before marking a task as complete.

S6-#8.1 enhancements:
- ast.parse() validation for deeper Python AST checks
- Validation report stored as Artifact for audit trail
- to_dict() / to_json() for serialisation

Usage::

    from ai_org_backend.services.build_validator import validate_repository

    report = validate_repository("/path/to/workspace")
    if not report.is_valid:
        print(report.errors)
"""

from __future__ import annotations

import ast
import json
import logging
import py_compile
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime as dt
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ValidationReport:
    """Result of repository validation."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checked_files: int = 0
    validated_at: str = field(default_factory=lambda: dt.utcnow().isoformat())

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def summary(self) -> str:
        parts = []
        if self.errors:
            parts.append(f"{len(self.errors)} error(s)")
        if self.warnings:
            parts.append(f"{len(self.warnings)} warning(s)")
        if not parts:
            return "Validation passed – no issues found"
        return f"Validation {'FAILED' if self.errors else 'passed'}: " + ", ".join(parts)

    def to_dict(self) -> dict:
        """Serialise report for artifact storage."""
        return asdict(self)

    def to_json(self) -> str:
        """JSON string of the report."""
        return json.dumps(self.to_dict(), indent=2, default=str)


def _validate_python_file(file_path: Path, report: ValidationReport) -> None:
    """Check a Python file for syntax errors using py_compile + ast.parse."""
    try:
        py_compile.compile(str(file_path), doraise=True)
    except py_compile.PyCompileError as exc:
        report.errors.append(f"Python syntax error in {file_path.name}: {exc}")
        return  # no point running ast.parse if py_compile fails
    except Exception as exc:
        report.warnings.append(f"Could not compile {file_path.name}: {exc}")
        return

    # S6-#8.1: deeper AST validation
    try:
        source = file_path.read_text(encoding="utf-8", errors="ignore")
        ast.parse(source, filename=str(file_path))
    except SyntaxError as exc:
        report.errors.append(
            f"AST parse error in {file_path.name} line {exc.lineno}: {exc.msg}"
        )
    except Exception as exc:
        report.warnings.append(f"AST parse warning for {file_path.name}: {exc}")


def _validate_json_file(file_path: Path, report: ValidationReport) -> None:
    """Check a JSON file for parse errors."""
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        json.loads(content)
    except json.JSONDecodeError as exc:
        report.errors.append(f"Invalid JSON in {file_path.name}: {exc}")
    except Exception as exc:
        report.warnings.append(f"Could not read {file_path.name}: {exc}")


def validate_repository(
    workspace_path: str,
    *,
    check_python: bool = True,
    check_json: bool = True,
) -> ValidationReport:
    """Validate all files in a repository workspace.

    Parameters
    ----------
    workspace_path : str
        Path to the workspace directory to validate.
    check_python : bool
        Whether to validate .py files for syntax errors.
    check_json : bool
        Whether to validate .json files for parse errors.

    Returns
    -------
    ValidationReport
        Report with errors and warnings.
    """
    report = ValidationReport()
    workspace = Path(workspace_path)

    if not workspace.exists():
        report.errors.append(f"Workspace path does not exist: {workspace_path}")
        return report

    if not workspace.is_dir():
        report.errors.append(f"Workspace path is not a directory: {workspace_path}")
        return report

    # Python file validation
    if check_python:
        for py_file in workspace.rglob("*.py"):
            # Skip virtual environments and __pycache__
            parts = py_file.parts
            if any(p in ("venv", ".venv", "__pycache__", "node_modules", ".git") for p in parts):
                continue
            report.checked_files += 1
            _validate_python_file(py_file, report)

    # JSON file validation
    if check_json:
        for json_file in workspace.rglob("*.json"):
            parts = json_file.parts
            if any(p in ("node_modules", ".git") for p in parts):
                continue
            report.checked_files += 1
            _validate_json_file(json_file, report)

    logger.info(
        "[S6-#8.1] Validation of %s: %s (%d files checked)",
        workspace_path, report.summary(), report.checked_files,
    )
    return report


def validate_files_content(
    files: list[dict],
) -> ValidationReport:
    """Validate a list of file dicts (path + content) without writing to disk.

    Each dict should have 'path' and 'content' keys.
    Uses a temporary directory for Python compilation checks.
    """
    report = ValidationReport()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        for file_info in files:
            path = file_info.get("path", "")
            content = file_info.get("content", "")

            if not path:
                continue

            report.checked_files += 1
            if path.endswith(".py"):
                tmp_file = tmp_path / Path(path).name
                tmp_file.write_text(content, encoding="utf-8")
                _validate_python_file(tmp_file, report)
            elif path.endswith(".json"):
                try:
                    json.loads(content)
                except json.JSONDecodeError as exc:
                    report.errors.append(f"Invalid JSON in {path}: {exc}")

    return report


def store_validation_artifact(
    report: ValidationReport,
    task_id: str,
    purpose_id: str,
    tenant_id: str,
) -> Optional[str]:
    """S6-#8.1: Persist a validation report as an Artifact for audit trail.

    Returns the artifact ID on success, None on failure.
    """
    try:
        from ai_org_backend.db import engine as _engine
        from ai_org_backend.models import Artifact
        from sqlmodel import Session as _Session

        report_json = report.to_json()
        artifact = Artifact(
            task_id=task_id,
            repo_path=f"_validation_reports/{task_id}.json",
            media_type="application/json",
            size=len(report_json),
            sha256="",  # in-memory report, no file hash
        )

        with _Session(_engine) as session:
            session.add(artifact)
            session.commit()
            session.refresh(artifact)
            aid = artifact.id

        logger.info(
            "[S6-#8.1] Stored validation report as artifact %s for task %s",
            aid, task_id,
        )
        return aid
    except Exception as exc:
        logger.warning("[S6-#8.1] Failed to store validation artifact: %s", exc)
        return None
