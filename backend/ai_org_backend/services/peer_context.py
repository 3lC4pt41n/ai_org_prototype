"""S5-A2: Peer Task Visibility Service.

Exposes to each Dev-Agent what peer agents are currently working on,
which files have been recently produced, and which API endpoints / DB
tables are claimed by other tasks — preventing duplication and conflicts.

Usage::

    from ai_org_backend.services.peer_context import get_peer_context

    ctx = get_peer_context(purpose_id, exclude_task_id=my_task_id)
    # → {"running_tasks": [...], "recent_files": [...], "claimed_endpoints": [...]}
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import desc
from sqlmodel import Session, select

from ai_org_backend.db import engine
from ai_org_backend.models import Artifact, Task, TaskStatus

logger = logging.getLogger(__name__)

# Regex patterns to extract API endpoints and DB tables from code/descriptions
_ENDPOINT_PATTERN = re.compile(
    r"""(?:@(?:router|app)\.\w+\s*\(\s*["'](\/[^"']+)["'])"""
    r"""|(?:prefix\s*=\s*["'](\/[^"']+)["'])""",
    re.IGNORECASE,
)
_TABLE_PATTERN = re.compile(
    r"""(?:__tablename__\s*=\s*["'](\w+)["'])"""
    r"""|(?:class\s+\w+.*table\s*=\s*True)""",
    re.IGNORECASE,
)


@dataclass
class PeerContext:
    """Context about what peer agents are doing for the same purpose."""

    running_tasks: list[dict] = field(default_factory=list)
    recent_files: list[str] = field(default_factory=list)
    claimed_endpoints: list[str] = field(default_factory=list)
    claimed_tables: list[str] = field(default_factory=list)
    completed_task_summaries: list[str] = field(default_factory=list)
    # S-Sprint4 Fix #23: Hard constraints – files forbidden for this agent
    forbidden_files: list[str] = field(default_factory=list)

    def to_prompt_text(self) -> str:
        """Format for injection into an agent prompt template."""
        sections: list[str] = []

        # S-Sprint4 Fix #23: Forbidden files as MANDATORY constraint (not advisory)
        if self.forbidden_files:
            file_list = "\n".join(f"- {f}" for f in self.forbidden_files)
            sections.append(
                "### FORBIDDEN FILES — HARD CONSTRAINT\n"
                "Du DARFST NICHT in folgende Dateien schreiben. "
                "Wenn du eine dieser Dateien ändern musst, erstelle stattdessen "
                "eine neue Datei mit dem Suffix _<task_id>.\n"
                f"{file_list}"
            )

        if self.running_tasks:
            lines = []
            for t in self.running_tasks:
                lines.append(f"- [{t['status']}] {t['description']} (owner: {t['owner']})")
            sections.append("### Currently Running Peer Tasks\n" + "\n".join(lines))

        if self.recent_files:
            sections.append(
                "### Recently Created Files\n" + "\n".join(f"- {f}" for f in self.recent_files)
            )

        if self.claimed_endpoints:
            sections.append(
                "### API Endpoints Claimed by Peers\n"
                + "\n".join(f"- {e}" for e in self.claimed_endpoints)
            )

        if self.claimed_tables:
            sections.append(
                "### Database Tables Claimed by Peers\n"
                + "\n".join(f"- {t}" for t in self.claimed_tables)
            )

        if self.completed_task_summaries:
            sections.append(
                "### Recently Completed Tasks\n"
                + "\n".join(f"- {s}" for s in self.completed_task_summaries)
            )

        if not sections:
            return ""

        return "## Peer Context (avoid conflicts!)\n\n" + "\n\n".join(sections)


def get_peer_context(
    purpose_id: str,
    *,
    exclude_task_id: Optional[str] = None,
    max_recent_files: int = 20,
    max_completed: int = 10,
) -> PeerContext:
    """S5-A2: Build peer-visibility context for a Dev-Agent.

    Parameters
    ----------
    purpose_id : str
        The purpose to query peer tasks for.
    exclude_task_id : str, optional
        The calling agent's own task ID (excluded from results).
    max_recent_files : int
        Maximum number of recently created files to return.
    max_completed : int
        Maximum number of recently completed task summaries.
    """
    ctx = PeerContext()

    with Session(engine) as session:
        # 1. Currently running tasks (status = doing)
        running_q = select(Task).where(
            Task.purpose_id == purpose_id,
            Task.status == TaskStatus.DOING,
        )
        if exclude_task_id:
            running_q = running_q.where(Task.id != exclude_task_id)

        for task in session.exec(running_q).all():
            ctx.running_tasks.append({
                "id": task.id,
                "description": task.description,
                "owner": task.owner or task.agent_role or "unknown",
                "status": task.status,
            })

        # 2. Recently created files (artifacts from completed tasks)
        recent_artifacts = session.exec(
            select(Artifact)
            .join(Task, Task.id == Artifact.task_id)
            .where(Task.purpose_id == purpose_id)
            .where(Task.status == TaskStatus.DONE)
            .order_by(desc(Artifact.created_at))
            .limit(max_recent_files)
        ).all()

        seen_paths: set[str] = set()
        for art in recent_artifacts:
            if exclude_task_id and art.task_id == exclude_task_id:
                continue
            path = art.repo_path or ""
            if path and path not in seen_paths:
                ctx.recent_files.append(path)
                seen_paths.add(path)

        # 3. Extract claimed API endpoints from artifact content
        for art in recent_artifacts:
            if not art.repo_path or not art.repo_path.endswith((".py", ".ts", ".js")):
                continue
            try:
                from ai_org_backend.services.storage import resolve_for_read
                file_path = resolve_for_read(art.repo_path)
                content = file_path.read_text(encoding="utf-8", errors="ignore")[:5000]
                for match in _ENDPOINT_PATTERN.finditer(content):
                    endpoint = match.group(1) or match.group(2)
                    if endpoint and endpoint not in ctx.claimed_endpoints:
                        ctx.claimed_endpoints.append(endpoint)
                for match in _TABLE_PATTERN.finditer(content):
                    table = match.group(1)
                    if table and table not in ctx.claimed_tables:
                        ctx.claimed_tables.append(table)
            except Exception:
                continue

        # S-Sprint4 Fix #23: Load forbidden files from FileReservation
        try:
            from ai_org_backend.services.file_reservation import get_claimed_files
            claimed = get_claimed_files(purpose_id, exclude_task_id=exclude_task_id)
            ctx.forbidden_files = [c["file_path"] for c in claimed]
        except Exception as exc:
            logger.warning("[S4-#23] Failed to load file reservations: %s", exc)

        # 4. Recently completed task summaries
        completed_tasks = session.exec(
            select(Task).where(
                Task.purpose_id == purpose_id,
                Task.status == TaskStatus.DONE,
            )
            .order_by(desc(Task.created_at))
            .limit(max_completed)
        ).all()
        for task in completed_tasks:
            if exclude_task_id and task.id == exclude_task_id:
                continue
            ctx.completed_task_summaries.append(
                f"{task.description} (owner: {task.owner or 'unknown'})"
            )

    return ctx
