"""S5-B1 / S5-B3: Code Review Blocking Gate & Re-Review Loop.

Transforms code review from advisory to a blocking enforcement gate:

- Parses review output for severity-tagged findings.
- Critical/High findings create REVIEW_FIX_TASK that blocks merge.
- After fix tasks complete, re-review is dispatched automatically (S5-B3).
- Max 3 review rounds enforced to prevent infinite loops.
- Findings are persisted to ``code_review_finding`` table (S5-B4).

Usage::

    from ai_org_backend.services.review_gate import (
        parse_review_findings,
        enforce_review_gate,
        dispatch_re_review,
    )
"""

from __future__ import annotations

import logging
import re
from datetime import datetime as dt
from typing import Optional

from sqlmodel import Session, select

from ai_org_backend.db import engine
from ai_org_backend.models import Task, TaskDependency, TaskOwner, TaskStatus
from ai_org_backend.models.code_review_finding import (
    CodeReviewFinding,
    FindingCategory,
    FindingSeverity,
)

logger = logging.getLogger(__name__)

# S5-B3: Maximum review rounds before escalation
MAX_REVIEW_ROUNDS = 3

# Regex patterns to extract structured findings from review markdown
_SEVERITY_PATTERN = re.compile(
    r"\*?\*?\[?(CRITICAL|HIGH|MEDIUM|LOW)\]?\*?\*?\s*[:\-–]?\s*(.+)",
    re.IGNORECASE,
)
_FILE_LINE_PATTERN = re.compile(
    r"(?:in|file|at)\s+[`'\"]?([^\s`'\"]+\.\w+)[`'\"]?"
    r"(?:\s*(?:line|L|:)\s*(\d+))?",
    re.IGNORECASE,
)
_CATEGORY_KEYWORDS: dict[str, FindingCategory] = {
    "security": FindingCategory.SECURITY,
    "injection": FindingCategory.SECURITY,
    "xss": FindingCategory.SECURITY,
    "auth": FindingCategory.SECURITY,
    "performance": FindingCategory.PERFORMANCE,
    "slow": FindingCategory.PERFORMANCE,
    "memory": FindingCategory.PERFORMANCE,
    "bug": FindingCategory.CORRECTNESS,
    "error": FindingCategory.ERROR_HANDLING,
    "exception": FindingCategory.ERROR_HANDLING,
    "naming": FindingCategory.NAMING,
    "convention": FindingCategory.STYLE,
    "style": FindingCategory.STYLE,
    "test": FindingCategory.TESTING,
    "coverage": FindingCategory.TESTING,
    "dependency": FindingCategory.DEPENDENCY,
    "import": FindingCategory.DEPENDENCY,
    "architecture": FindingCategory.ARCHITECTURE,
    "coupling": FindingCategory.ARCHITECTURE,
}


def _classify_category(text: str) -> str:
    """Infer finding category from description text."""
    lower = text.lower()
    for keyword, cat in _CATEGORY_KEYWORDS.items():
        if keyword in lower:
            return cat.value
    return FindingCategory.OTHER.value


def parse_review_findings(
    review_md: str,
    task_id: str,
    purpose_id: str,
    tenant_id: str,
) -> list[CodeReviewFinding]:
    """Parse code-review markdown output into structured findings.

    Looks for severity-tagged lines like:
        [CRITICAL] SQL injection in user_handler.py line 42
        **HIGH**: Missing input validation in api/routes.py

    Returns list of CodeReviewFinding objects (not yet persisted).
    """
    findings: list[CodeReviewFinding] = []

    for line in review_md.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        m = _SEVERITY_PATTERN.search(line)
        if not m:
            continue

        severity = m.group(1).lower()
        description = m.group(2).strip()

        # Extract file/line if present
        file_path = None
        line_number = None
        fm = _FILE_LINE_PATTERN.search(description)
        if fm:
            file_path = fm.group(1)
            if fm.group(2):
                try:
                    line_number = int(fm.group(2))
                except ValueError:
                    pass

        finding = CodeReviewFinding(
            task_id=task_id,
            purpose_id=purpose_id,
            tenant_id=tenant_id,
            severity=severity,
            category=_classify_category(description),
            description=description,
            file_path=file_path,
            line_number=line_number,
        )
        findings.append(finding)

    return findings


def persist_findings(findings: list[CodeReviewFinding]) -> int:
    """S5-B4: Save findings to the database. Returns count persisted."""
    if not findings:
        return 0
    with Session(engine) as session:
        for f in findings:
            session.add(f)
        session.commit()
    logger.info("[S5-B4] Persisted %d code review findings", len(findings))
    return len(findings)


def enforce_review_gate(
    review_task_id: str,
    review_md: str,
    purpose_id: str,
    tenant_id: str,
) -> dict:
    """S5-B1: Enforce code-review as a blocking gate.

    1. Parse findings from the review markdown.
    2. Persist all findings to the database.
    3. For Critical/High findings, create fix tasks with blocking deps.
    4. Update the review task's ``code_review_status`` accordingly.

    Returns a summary dict with counts and fix task IDs.
    """
    findings = parse_review_findings(review_md, review_task_id, purpose_id, tenant_id)

    # Snapshot finding metadata before persist_findings detaches objects
    finding_metas = [
        {
            "id": f.id,
            "severity": f.severity,
            "description": f.description,
            "file_path": f.file_path,
        }
        for f in findings
    ]
    persist_findings(findings)

    critical_count = sum(1 for m in finding_metas if m["severity"] == FindingSeverity.CRITICAL)
    high_count = sum(1 for m in finding_metas if m["severity"] == FindingSeverity.HIGH)
    blocking_count = critical_count + high_count

    fix_task_ids: list[str] = []

    with Session(engine) as session:
        review_task = session.get(Task, review_task_id)
        if not review_task:
            logger.error("[S5-B1] Review task %s not found", review_task_id)
            return {"error": "review task not found"}

        if blocking_count == 0:
            # All clean – approve
            review_task.code_review_status = "approved"
            session.add(review_task)
            session.commit()
            logger.info(
                "[S5-B1] Review %s approved (%d findings, none blocking)",
                review_task_id,
                len(finding_metas),
            )
            return {
                "status": "approved",
                "total_findings": len(finding_metas),
                "blocking": 0,
                "fix_tasks": [],
            }

        # Blocking findings → create fix tasks
        review_task.code_review_status = "changes_requested"
        session.add(review_task)

        blocking_metas = [
            m for m in finding_metas
            if m["severity"] in (FindingSeverity.CRITICAL, FindingSeverity.HIGH)
        ]

        # Group findings by file to avoid creating too many fix tasks
        file_groups: dict[str, list[dict]] = {}
        for m in blocking_metas:
            key = m["file_path"] or "general"
            file_groups.setdefault(key, []).append(m)

        for file_key, group in file_groups.items():
            desc_lines = [
                f"Fix {m['severity'].upper()}: {m['description']}"
                for m in group[:5]
            ]
            fix_desc = f"Review Fix: {file_key}\n" + "\n".join(desc_lines)
            if len(fix_desc) > 2000:
                fix_desc = fix_desc[:1997] + "..."

            fix_task = Task(
                tenant_id=tenant_id,
                purpose_id=purpose_id,
                description=fix_desc,
                status=TaskStatus.TODO,
                owner=TaskOwner.DEV,
                agent_role="dev",
                notes=f"Fix {len(group)} review findings in {file_key}",
            )
            session.add(fix_task)
            session.flush()

            # Block merge on this fix task
            session.add(TaskDependency(
                from_id=fix_task.id,
                to_id=review_task_id,
                dependency_type="blocks",
            ))

            # Update persisted findings with fix_task reference
            for m in group:
                existing = session.get(CodeReviewFinding, m["id"])
                if existing:
                    existing.fix_task_id = fix_task.id
                    session.add(existing)

            fix_task_ids.append(fix_task.id)

        session.commit()

    logger.info(
        "[S5-B1] Review %s: changes_requested (%d blocking, %d fix tasks created)",
        review_task_id,
        blocking_count,
        len(fix_task_ids),
    )

    return {
        "status": "changes_requested",
        "total_findings": len(finding_metas),
        "blocking": blocking_count,
        "fix_tasks": fix_task_ids,
    }


def dispatch_re_review(
    review_task_id: str,
    tenant_id: str,
) -> bool:
    """S5-B3: Dispatch a re-review after fix tasks complete.

    Checks the review round counter and either:
    - Dispatches the code-review agent again (round < MAX_REVIEW_ROUNDS)
    - Escalates to MANUAL_REVIEW status (round >= MAX_REVIEW_ROUNDS)

    Returns True if re-review was dispatched.
    """
    from ai_org_backend.tasks.celery_app import celery

    with Session(engine) as session:
        review_task = session.get(Task, review_task_id)
        if not review_task:
            logger.warning("[S5-B3] Review task %s not found", review_task_id)
            return False

        current_round = review_task.review_rounds + 1
        review_task.review_rounds = current_round

        if current_round >= MAX_REVIEW_ROUNDS:
            # Escalate to manual review
            review_task.code_review_status = "requires_manual_review"
            review_task.notes = (
                f"{review_task.notes} | escalated after {current_round} review rounds"
                if review_task.notes
                else f"escalated after {current_round} review rounds"
            )
            session.add(review_task)
            session.commit()
            logger.info(
                "[S5-B3] Review %s escalated to manual review after %d rounds",
                review_task_id,
                current_round,
            )
            return False

        # Reset review status for re-review
        review_task.code_review_status = "reviewing"
        review_task.status = TaskStatus.DOING
        session.add(review_task)
        session.commit()

    # Dispatch code-review agent
    try:
        celery.send_task(
            "agent.code_review",
            args=[tenant_id, review_task_id],
            queue=f"{tenant_id}:code_review",
        )
        logger.info(
            "[S5-B3] Re-review round %d dispatched for task %s",
            current_round,
            review_task_id,
        )
        return True
    except Exception as exc:
        logger.error("[S5-B3] Failed to dispatch re-review: %s", exc)
        return False


def check_fix_tasks_complete(review_task_id: str) -> bool:
    """Check if all fix tasks for a review are complete."""
    with Session(engine) as session:
        pending_fixes = session.exec(
            select(Task)
            .join(TaskDependency, TaskDependency.from_id == Task.id)
            .where(
                TaskDependency.to_id == review_task_id,
                Task.status != TaskStatus.DONE,
            )
        ).all()
        return len(pending_fixes) == 0
