from __future__ import annotations

"""Refactor agent suggesting improvements once tests pass."""

import logging  # noqa: E402
import re  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import List  # noqa: E402

from ai_org_backend.db import SessionLocal  # noqa: E402
from ai_org_backend.main import TASK_CNT, TASK_LAT, TOKEN_PRICE_PER_1000, Repo, debit  # noqa: E402
from ai_org_backend.metrics import prom_counter, prom_hist  # noqa: E402
from ai_org_backend.models import Artifact, Purpose, Task  # noqa: E402
from ai_org_backend.models.chat import ChatRole  # noqa: E402
from ai_org_backend.services.llm_client import MODEL_PRO, chat_with_tools  # noqa: E402
from ai_org_backend.services.storage import save_artefact  # noqa: E402
from ai_org_backend.tasks.celery_app import celery  # noqa: E402
from ai_org_backend.settings import settings  # noqa: E402

from .utils import load_template  # noqa: E402

REFACTOR_RUNS = prom_counter("ai_refactor_runs_total", "Refactor agent executions")
REFACTOR_LAT = prom_hist("ai_refactor_latency_seconds", "Refactor agent latency")

REFACTOR_PROMPT_TMPL = load_template("refactor.j2")


@celery.task(name="agent.refactor")
def refactor_task(tenant_id: str, task_id: str) -> None:
    """Analyze the codebase and suggest refactorings."""
    start = time.time()
    with SessionLocal() as session:
        task = session.get(Task, task_id)
        purpose = session.get(Purpose, task.purpose_id) if task else None
        if not task or not purpose:
            return
        artifacts = session.query(Artifact).join(Task).filter(Task.purpose_id == purpose.id).all()
    snippets: List[dict] = []
    MAX_TOKENS = 800
    for art in artifacts:
        path = art.repo_path or ""
        if any(skip in path for skip in ["requirements/", "blueprint", "reports/", "tests/"]):
            continue
        if not re.search(r"\.(py|js|jsx|ts|tsx|java|html|css)$", path, re.IGNORECASE):
            continue
        file_path = settings.workspace_dir / tenant_id / path
        try:
            code = file_path.read_text(encoding="utf-8")
        except (FileNotFoundError, PermissionError, UnicodeDecodeError):
            continue
        if len(code) <= MAX_TOKENS * 4:
            snippet = code.strip()
        else:
            lines = code.splitlines()
            snippet_lines = [
                ln for ln in lines if ln.strip().startswith(("def ", "class ")) or "TODO" in ln
            ]
            if not snippet_lines:
                snippet_lines = lines[:50]
            snippet = "\n".join(snippet_lines)
        lang = Path(path).suffix.lstrip(".") or ""
        snippets.append({"filename": path, "content": snippet, "language": lang})

    prompt = REFACTOR_PROMPT_TMPL.render(snippets=snippets)
    try:
        resp = chat_with_tools(
            messages=[{"role": ChatRole.USER.value, "content": prompt}],
            model=MODEL_PRO,
            temperature=0,
            tenant_id=tenant_id,
        )
        REFACTOR_RUNS.inc()
        suggestions_md = resp["choices"][0]["message"]["content"] if resp else ""
    except Exception as exc:  # pragma: no cover
        suggestions_md = f"*(Refactor analysis failed: {exc})*"
        resp = None
    finally:
        REFACTOR_LAT.observe(time.time() - start)

    if not suggestions_md.strip():
        suggestions_md = "_No refactoring suggestions (code may already be optimal)._"

    save_artefact(
        task_id,
        suggestions_md.encode("utf-8"),
        filename="reports/refactor_suggestions.md",
        allow_overwrite=True,
    )

    suggestions_count = suggestions_md.count("\n- ")
    notes_msg = f"refactor suggestions: {suggestions_count} item(s)"
    Repo(tenant_id).update(
        task_id,
        status="done",
        owner="QA-Refactor",
        notes=notes_msg,
        issues_found=suggestions_count,
        tokens_actual=resp.usage.total_tokens if resp and hasattr(resp, "usage") else 0,
    )
    tokens_used = resp.usage.total_tokens if resp and hasattr(resp, "usage") else 0
    try:
        debit(
            tenant_id,
            tokens_used * (TOKEN_PRICE_PER_1000 / 1000.0),
            task.purpose_id if task else None,
        )
    except Exception as e:
        logging.error(f"[RefactorAgent] Budget debit failed for task {task_id}: {e}")
    TASK_CNT.labels(tenant_id, "qa-refactor", "done").inc()
    TASK_LAT.labels("qa-refactor", tenant_id).observe(time.time() - start)
