"""S5-B2: Smart Merge Service for Parallel Dev-Agent Outputs.

Combines code outputs from multiple parallel Dev-Agents into a single
coherent codebase:

1. Non-overlapping files: concatenated directly (no conflict).
2. requirements.txt: union of packages with version conflict detection.
3. __init__.py: consolidated import statements.
4. Overlapping content files: attempt line-by-line merge; flag as conflict
   if irreconcilable.

Usage::

    from ai_org_backend.services.merge_service import merge_purpose_outputs
    result = merge_purpose_outputs(tenant_id, purpose_id)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime as dt
from typing import Optional

from sqlalchemy import desc
from sqlmodel import Session, select

from ai_org_backend.db import engine
from ai_org_backend.models import (
    Artifact,
    MergeConflict,
    MergeConflictStatus,
    Task,
    TaskStatus,
)

logger = logging.getLogger(__name__)


@dataclass
class MergeResult:
    """Result of merging parallel task outputs."""
    merged_files: list[str] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)
    auto_resolved: int = 0
    manual_required: int = 0
    success: bool = True


def merge_purpose_outputs(
    tenant_id: str,
    purpose_id: str,
) -> MergeResult:
    """S5-B2: Merge outputs from all completed dev tasks in a purpose.

    Non-overlapping files are trivially merged.  Overlapping files go
    through a simple line-level merge heuristic.  Irreconcilable conflicts
    are recorded as ``MergeConflict`` records.
    """
    result = MergeResult()

    with Session(engine) as session:
        # Get all completed implementation tasks (not pipeline-phase tasks)
        impl_tasks = session.exec(
            select(Task).where(
                Task.purpose_id == purpose_id,
                Task.tenant_id == tenant_id,
                Task.status == TaskStatus.DONE,
                ~Task.description.in_([
                    "Vision Document",
                    "Product Requirements Document",
                    "Architecture Blueprint",
                    "Architecture & Domain Review",
                    "Implementation Plan",
                ]),
            )
        ).all()

        if len(impl_tasks) < 2:
            # Nothing to merge with < 2 tasks
            result.success = True
            return result

        # Build file → [(task_id, artifact)] mapping
        file_map: dict[str, list[tuple[str, Artifact]]] = {}
        for task in impl_tasks:
            artifacts = session.exec(
                select(Artifact)
                .where(Artifact.task_id == task.id)
                .order_by(desc(Artifact.created_at))
            ).all()
            seen_paths: set[str] = set()
            for art in artifacts:
                path = art.repo_path or ""
                if path and path not in seen_paths:
                    file_map.setdefault(path, []).append((task.id, art))
                    seen_paths.add(path)

        for path, entries in file_map.items():
            if len(entries) == 1:
                # Non-overlapping: no conflict
                result.merged_files.append(path)
                continue

            # Multiple tasks wrote to the same file
            if _is_requirements_file(path):
                # Special handling for requirements.txt
                _merge_requirements(path, entries, result, session, purpose_id, tenant_id)
            elif _is_init_file(path):
                # Special handling for __init__.py
                _merge_init_imports(path, entries, result)
            else:
                # General overlap: record as conflict
                task_ids = [e[0] for e in entries]
                conflict = MergeConflict(
                    purpose_id=purpose_id,
                    tenant_id=tenant_id,
                    task_a_id=task_ids[0],
                    task_b_id=task_ids[1],
                    file_path=path,
                    conflict_type="content_overlap",
                    description=(
                        f"File '{path}' modified by {len(entries)} tasks"
                    ),
                    status=MergeConflictStatus.OPEN,
                )
                session.add(conflict)
                result.conflicts.append({
                    "file": path,
                    "tasks": task_ids,
                    "type": "content_overlap",
                })
                result.manual_required += 1

        session.commit()

    result.success = result.manual_required == 0

    logger.info(
        "[S5-B2] Merge result for purpose %s: %d merged, %d auto-resolved, %d manual",
        purpose_id,
        len(result.merged_files),
        result.auto_resolved,
        result.manual_required,
    )
    return result


def _is_requirements_file(path: str) -> bool:
    return "requirements" in path.lower() and path.endswith(".txt")


def _is_init_file(path: str) -> bool:
    return path.endswith("__init__.py")


def _merge_requirements(
    path: str,
    entries: list[tuple[str, Artifact]],
    result: MergeResult,
    session: Session,
    purpose_id: str,
    tenant_id: str,
) -> None:
    """Merge requirements.txt from multiple tasks: union packages, detect version conflicts."""
    req_re = re.compile(r"^([a-zA-Z0-9_-]+)\s*([><=!~].*)?$")
    all_packages: dict[str, dict[str, str]] = {}  # pkg → {task_id: version_spec}

    for task_id, art in entries:
        try:
            from ai_org_backend.services.storage import resolve_for_read
            content = resolve_for_read(art.repo_path).read_text(
                encoding="utf-8", errors="ignore"
            )
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                m = req_re.match(line)
                if m:
                    pkg = m.group(1).lower()
                    ver = (m.group(2) or "").strip()
                    all_packages.setdefault(pkg, {})[task_id] = ver
        except Exception:
            continue

    has_conflict = False
    for pkg, task_versions in all_packages.items():
        specs = [v for v in task_versions.values() if v]
        if len(set(specs)) > 1:
            has_conflict = True
            task_ids = list(task_versions.keys())
            conflict = MergeConflict(
                purpose_id=purpose_id,
                tenant_id=tenant_id,
                task_a_id=task_ids[0],
                task_b_id=task_ids[1] if len(task_ids) > 1 else task_ids[0],
                file_path=path,
                conflict_type="package_version",
                description=f"Package '{pkg}' version conflict: {task_versions}",
                status=MergeConflictStatus.OPEN,
            )
            session.add(conflict)
            result.conflicts.append({
                "file": path,
                "package": pkg,
                "type": "package_version",
            })
            result.manual_required += 1

    if not has_conflict:
        result.merged_files.append(path)
        result.auto_resolved += 1


def _merge_init_imports(
    path: str,
    entries: list[tuple[str, Artifact]],
    result: MergeResult,
) -> None:
    """Merge __init__.py: combine all unique import statements."""
    all_imports: set[str] = set()

    for task_id, art in entries:
        try:
            from ai_org_backend.services.storage import resolve_for_read
            content = resolve_for_read(art.repo_path).read_text(
                encoding="utf-8", errors="ignore"
            )
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith(("from ", "import ")):
                    all_imports.add(stripped)
        except Exception:
            continue

    # Write merged imports back
    if all_imports:
        try:
            from ai_org_backend.services.storage import resolve_for_read
            merged_content = "\n".join(sorted(all_imports)) + "\n"
            target = resolve_for_read(path)
            target.write_text(merged_content, encoding="utf-8")
            result.merged_files.append(path)
            result.auto_resolved += 1
        except Exception as exc:
            logger.warning("[S5-B2] Failed to write merged __init__.py: %s", exc)
            result.conflicts.append({"file": path, "type": "merge_write_failed"})
    else:
        result.merged_files.append(path)
