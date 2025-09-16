from __future__ import annotations

"""
Reviewer Agent (Architecture + Domain) — tenant-aware
----------------------------------------------------
Generates a concise review of the architecture blueprint and domain model.
Produces a Markdown artefact. **Does not** mark the task done — the user
must approve via the Reviews API to unblock downstream tasks.
"""
import logging  # noqa: E402
from typing import Optional  # noqa: E402

from sqlalchemy import desc  # noqa: E402

from ai_org_backend.db import SessionLocal  # noqa: E402

# Small metrics parity (keeps style with other agents)
from ai_org_backend.metrics import prom_counter, prom_hist  # noqa: E402
from ai_org_backend.models import Purpose  # noqa: E402
from ai_org_backend.models.chat import ChatRole  # noqa: E402
from ai_org_backend.repo import Repo  # noqa: E402
from ai_org_backend.services.llm_client import MODEL_PRO, chat_with_tools  # noqa: E402
from ai_org_backend.services.storage import save_artefact  # noqa: E402
from ai_org_backend.tasks.celery_app import celery  # noqa: E402

from .utils import load_template  # noqa: E402

REVIEW_RUNS = prom_counter("ai_review_runs_total", "Review agent executions")
REVIEW_LAT = prom_hist("ai_review_latency_seconds", "Review agent latency")

PROMPT_TMPL = load_template("review.j2")


def _call_llm(messages, tenant_id: Optional[str]) -> Optional[dict]:
    """
    Robustly call the LLM. If your llm_client supports tenant-billing, we pass tenant.
    If not, we fall back gracefully without the kwarg.
    """
    try:
        # Preferred: budget-aware billing
        return chat_with_tools(
            messages=messages, model=MODEL_PRO, temperature=0, tenant_id=tenant_id
        )
    except TypeError:
        # Fallback: older signature without 'tenant_id'
        return chat_with_tools(messages=messages, model=MODEL_PRO, temperature=0)


def run_reviewer(purpose_id: str, blueprint_md: str) -> str:
    """
    Run the reviewer synchronously and return Markdown content.
    """
    import time

    with SessionLocal() as s:
        purpose = s.get(Purpose, purpose_id)
        if not purpose:
            return "⚠️ Purpose not found; cannot review."
        ctx = {
            "purpose_name": purpose.name,
            "tenant_id": purpose.tenant_id,
            "blueprint": blueprint_md,
        }
        prompt = PROMPT_TMPL.render(**ctx)
        start = time.time()
        try:
            resp = _call_llm(
                [{"role": ChatRole.USER.value, "content": prompt}], tenant_id=purpose.tenant_id
            )
            REVIEW_RUNS.inc()
            if not resp:
                return "⚠️ Budget exhausted or LLM unavailable; unable to generate review."
            return resp["choices"][0]["message"]["content"]
        finally:
            REVIEW_LAT.observe(time.time() - start)


@celery.task(name="agent.reviewer")
def reviewer_task(
    tenant_id: str, purpose_id: str, blueprint_task_id: str, review_task_id: str
) -> None:
    """
    Celery entrypoint — creates the Markdown review artefact for the given review task.
    Leaves the task in 'todo' (awaiting approval).
    """
    logging.info("[Reviewer] Generating review for purpose=%s (tenant=%s)", purpose_id, tenant_id)
    purpose_auto_mode = False
    with SessionLocal() as s:
        # Fetch blueprint content from its artefact(s)
        # Simplicity: we read the latest blueprint artefact saved for blueprint task.
        from ai_org_backend.models import Artefact

        blueprint_text = ""
        try:
            purpose = s.get(Purpose, purpose_id)
            if purpose and getattr(purpose, "mode", None) == "auto":
                purpose_auto_mode = True
            # Most recent artefact for the blueprint task (markdown)
            art = (
                s.query(Artefact)
                .filter(Artefact.task_id == blueprint_task_id)
                .order_by(desc(Artefact.created_at))
                .first()
            )
            if art:
                from ai_org_backend.services.storage import resolve_for_read

                file_path = resolve_for_read(art.repo_path)
                blueprint_text = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            logging.error("[Reviewer] Failed to load blueprint artefact: %s", e)
            blueprint_text = ""

    review_md = run_reviewer(purpose_id, blueprint_text)

    # Persist the review artefact (keep task status todo; user will approve)
    try:
        save_artefact(
            review_task_id,
            review_md.encode("utf-8"),
            filename="reviews/architecture_domain_review.md",
            allow_overwrite=True,
            media_type="text/markdown",
        )
        logging.info("[Reviewer] Review artefact saved for task=%s", review_task_id)
    except Exception as e:
        logging.error("[Reviewer] Failed to save review artefact for task=%s: %s", review_task_id, e)
        return

    if purpose_auto_mode:
        try:
            Repo(tenant_id).update(
                review_task_id,
                status="done",
                owner="Review",
                notes="approved",
            )
            logging.info(
                "[Reviewer] Auto-approved review task %s (purpose %s)",
                review_task_id,
                purpose_id,
            )
        except Exception as e:
            logging.error(
                "[Reviewer] Failed to auto-approve review task %s: %s",
                review_task_id,
                e,
            )
