from __future__ import annotations

"""Code Review agent that inspects repository code for quality issues."""

import logging  # noqa: E402
import re  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import List  # noqa: E402

from ai_org_backend.db import SessionLocal  # noqa: E402
from ai_org_backend.main import TASK_CNT, TASK_LAT, TOKEN_PRICE_PER_1000, Repo, debit  # noqa: E402
from ai_org_backend.metrics import prom_counter, prom_hist  # noqa: E402
from ai_org_backend.models import Artifact, Purpose, Task, TaskOwner  # noqa: E402
from ai_org_backend.models.chat import ChatRole  # noqa: E402
from ai_org_backend.services.llm_client import MODEL_PRO, chat_with_tools  # noqa: E402
from ai_org_backend.services.storage import register_artefact  # noqa: E402
from ai_org_backend.tasks.celery_app import celery  # noqa: E402
from ai_org_backend.settings import settings  # noqa: E402

from .utils import load_template  # noqa: E402

CODE_REVIEW_RUNS = prom_counter("ai_code_review_runs_total", "Code review agent executions")
CODE_REVIEW_LAT = prom_hist("ai_code_review_latency_seconds", "Code review agent latency")

PROMPT_TMPL = load_template("code_review.j2")


@celery.task(name="agent.code_review")
def code_review_task(tenant_id: str, task_id: str) -> None:
    """Analyze the codebase and record a review report."""
    start = time.time()
    with SessionLocal() as session:
        task = session.get(Task, task_id)
        purpose = session.get(Purpose, task.purpose_id) if task else None
        if not task or not purpose:
            return
        purpose_name = purpose.name
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

    context = {"purpose_name": purpose_name, "snippets": snippets}
    prompt_template = PROMPT_TMPL
    if task and task.prompt_template:
        try:
            prompt_template = load_template(task.prompt_template)
        except FileNotFoundError:
            logging.warning(
                "[CodeReviewAgent] Prompt %s not found; using default",
                task.prompt_template,
            )
        except Exception:
            logging.exception(
                "[CodeReviewAgent] Failed to load prompt %s",
                task.prompt_template,
            )
    prompt = prompt_template.render(**context)
    try:
        resp = chat_with_tools(
            messages=[{"role": ChatRole.USER.value, "content": prompt}],
            model=MODEL_PRO,
            temperature=0,
            tenant_id=tenant_id,
        )
        CODE_REVIEW_RUNS.inc()
        review_md = resp["choices"][0]["message"]["content"] if resp else ""
    except Exception as exc:  # pragma: no cover
        review_md = f"*(Code review failed: {exc})*"
        resp = None
    finally:
        CODE_REVIEW_LAT.observe(time.time() - start)

    if not review_md.strip():
        review_md = "_No review output (LLM may have been unavailable)._"

    register_artefact(
        task_id,
        review_md.encode("utf-8"),
        filename="reviews/code_review.md",
        allow_overwrite=True,
    )

    issues_found = review_md.count("\n- ")
    notes_msg = (
        f"code review completed, {issues_found} issue(s) noted"
        if issues_found
        else "code review clean"
    )
    Repo(tenant_id).update(
        task_id,
        status="done",
        owner=TaskOwner.QA_REVIEW,
        notes=notes_msg,
        issues_found=issues_found,
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
        logging.error(f"[CodeReviewAgent] Budget debit failed for task {task_id}: {e}")
    TASK_CNT.labels(tenant_id, "qa-review", "done").inc()
    TASK_LAT.labels("qa-review", tenant_id).observe(time.time() - start)
