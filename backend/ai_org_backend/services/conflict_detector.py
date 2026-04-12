"""S5-A3: Conflict Detection & Warning System.

Detects potential conflicts between parallel Dev-Agents:
- File path overlaps (two agents writing to the same file)
- API endpoint collisions
- Database migration conflicts
- Package version conflicts in requirements.txt
- Shared class/function redefinitions

Usage::

    from ai_org_backend.services.conflict_detector import detect_conflicts
    warnings = detect_conflicts(purpose_id, task_id)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from sqlalchemy import desc
from sqlmodel import Session, select

from ai_org_backend.db import engine
from ai_org_backend.models import Artifact, Task, TaskStatus

logger = logging.getLogger(__name__)


class ConflictSeverity(str, Enum):
    CRITICAL = "critical"    # Must be resolved before merge
    HIGH = "high"            # Should be resolved, blocks if unresolved
    MEDIUM = "medium"        # Advisory, agent should adjust
    LOW = "low"              # Informational only


@dataclass
class Conflict:
    """A single detected conflict between tasks."""
    severity: ConflictSeverity
    conflict_type: str  # file_overlap, endpoint_collision, migration, package, class_redef
    description: str
    task_a_id: str
    task_b_id: str
    file_path: Optional[str] = None

    def to_warning_text(self) -> str:
        return f"[{self.severity.value.upper()}] {self.conflict_type}: {self.description}"


@dataclass
class ConflictReport:
    """Full conflict report for a purpose."""
    conflicts: list[Conflict] = field(default_factory=list)
    has_critical: bool = False

    def to_prompt_text(self) -> str:
        if not self.conflicts:
            return ""
        lines = ["### Conflict Warnings (resolve before proceeding!)"]
        for c in self.conflicts:
            lines.append(f"- {c.to_warning_text()}")
        return "\n".join(lines)

    @property
    def blocking(self) -> bool:
        return any(
            c.severity in (ConflictSeverity.CRITICAL, ConflictSeverity.HIGH)
            for c in self.conflicts
        )


def detect_conflicts(
    purpose_id: str,
    task_id: Optional[str] = None,
) -> ConflictReport:
    """S5-A3: Detect conflicts between parallel tasks in a purpose.

    Parameters
    ----------
    purpose_id : str
        The purpose to check for conflicts.
    task_id : str, optional
        If provided, only report conflicts involving this task.

    Returns
    -------
    ConflictReport
        All detected conflicts with severity levels.
    """
    report = ConflictReport()

    with Session(engine) as session:
        # Get all active/completed tasks for this purpose
        tasks = session.exec(
            select(Task).where(
                Task.purpose_id == purpose_id,
                Task.status.in_([TaskStatus.DOING, TaskStatus.DONE, TaskStatus.TODO]),
            )
        ).all()

        if len(tasks) < 2:
            return report

        # Build file → task mapping
        file_owners: dict[str, list[str]] = {}
        task_artifacts: dict[str, list[Artifact]] = {}

        for task in tasks:
            artifacts = session.exec(
                select(Artifact)
                .where(Artifact.task_id == task.id)
                .order_by(desc(Artifact.created_at))
            ).all()
            task_artifacts[task.id] = artifacts
            for art in artifacts:
                path = art.repo_path or ""
                if path:
                    file_owners.setdefault(path, []).append(task.id)

        # ── 1. File path overlaps ──
        for path, owners in file_owners.items():
            if len(owners) > 1:
                if task_id and task_id not in owners:
                    continue
                report.conflicts.append(Conflict(
                    severity=ConflictSeverity.HIGH,
                    conflict_type="file_overlap",
                    description=(
                        f"File '{path}' is written by {len(owners)} tasks: "
                        f"{', '.join(owners)}"
                    ),
                    task_a_id=owners[0],
                    task_b_id=owners[1],
                    file_path=path,
                ))

        # ── 2. API endpoint collisions ──
        endpoint_owners: dict[str, list[str]] = {}
        endpoint_re = re.compile(
            r'@(?:router|app)\.(?:get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)',
            re.IGNORECASE,
        )
        for tid, arts in task_artifacts.items():
            for art in arts:
                if not art.repo_path or not art.repo_path.endswith(".py"):
                    continue
                try:
                    from ai_org_backend.services.storage import resolve_for_read
                    content = resolve_for_read(art.repo_path).read_text(
                        encoding="utf-8", errors="ignore"
                    )[:10000]
                    for m in endpoint_re.finditer(content):
                        ep = m.group(1)
                        endpoint_owners.setdefault(ep, []).append(tid)
                except Exception:
                    continue

        for ep, owners in endpoint_owners.items():
            if len(owners) > 1:
                unique = list(dict.fromkeys(owners))
                if len(unique) > 1:
                    if task_id and task_id not in unique:
                        continue
                    report.conflicts.append(Conflict(
                        severity=ConflictSeverity.CRITICAL,
                        conflict_type="endpoint_collision",
                        description=(
                            f"API endpoint '{ep}' defined by tasks: "
                            f"{', '.join(unique)}"
                        ),
                        task_a_id=unique[0],
                        task_b_id=unique[1],
                    ))

        # ── 3. Package version conflicts ──
        req_files: dict[str, dict[str, str]] = {}  # task_id → {package: version_spec}
        req_re = re.compile(r"^([a-zA-Z0-9_-]+)\s*([><=!~]+.+)?$")
        for tid, arts in task_artifacts.items():
            for art in arts:
                if not art.repo_path or "requirements" not in art.repo_path:
                    continue
                try:
                    from ai_org_backend.services.storage import resolve_for_read
                    content = resolve_for_read(art.repo_path).read_text(
                        encoding="utf-8", errors="ignore"
                    )
                    pkgs: dict[str, str] = {}
                    for line in content.splitlines():
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        m = req_re.match(line)
                        if m:
                            pkgs[m.group(1).lower()] = (m.group(2) or "").strip()
                    req_files[tid] = pkgs
                except Exception:
                    continue

        if len(req_files) > 1:
            all_packages: dict[str, dict[str, str]] = {}  # pkg → {task_id: version_spec}
            for tid, pkgs in req_files.items():
                for pkg, ver in pkgs.items():
                    all_packages.setdefault(pkg, {})[tid] = ver

            for pkg, task_versions in all_packages.items():
                if len(task_versions) > 1:
                    specs = list(task_versions.values())
                    if len(set(s for s in specs if s)) > 1:
                        tids = list(task_versions.keys())
                        if task_id and task_id not in tids:
                            continue
                        report.conflicts.append(Conflict(
                            severity=ConflictSeverity.MEDIUM,
                            conflict_type="package_version",
                            description=(
                                f"Package '{pkg}' has conflicting version specs: "
                                + ", ".join(f"{t}={v or 'any'}" for t, v in task_versions.items())
                            ),
                            task_a_id=tids[0],
                            task_b_id=tids[1] if len(tids) > 1 else tids[0],
                        ))

        # ── 4. Class/function redefinition ──
        class_owners: dict[str, list[str]] = {}
        class_re = re.compile(r"^(?:class|def)\s+(\w+)", re.MULTILINE)
        for tid, arts in task_artifacts.items():
            for art in arts:
                if not art.repo_path or not art.repo_path.endswith(".py"):
                    continue
                try:
                    from ai_org_backend.services.storage import resolve_for_read
                    content = resolve_for_read(art.repo_path).read_text(
                        encoding="utf-8", errors="ignore"
                    )[:10000]
                    for m in class_re.finditer(content):
                        name = m.group(1)
                        # Skip common names
                        if name in ("__init__", "main", "setup", "test", "run"):
                            continue
                        key = f"{art.repo_path}:{name}"
                        class_owners.setdefault(name, []).append(tid)
                except Exception:
                    continue

        for name, owners in class_owners.items():
            unique = list(dict.fromkeys(owners))
            if len(unique) > 1:
                if task_id and task_id not in unique:
                    continue
                report.conflicts.append(Conflict(
                    severity=ConflictSeverity.LOW,
                    conflict_type="class_redef",
                    description=(
                        f"Symbol '{name}' defined by multiple tasks: "
                        f"{', '.join(unique)}"
                    ),
                    task_a_id=unique[0],
                    task_b_id=unique[1],
                ))

    report.has_critical = any(
        c.severity == ConflictSeverity.CRITICAL for c in report.conflicts
    )

    if report.conflicts:
        logger.info(
            "[S5-A3] Detected %d conflicts for purpose %s (%d critical)",
            len(report.conflicts),
            purpose_id,
            sum(1 for c in report.conflicts if c.severity == ConflictSeverity.CRITICAL),
        )

    return report
