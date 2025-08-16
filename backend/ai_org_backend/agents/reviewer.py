from __future__ import annotations
"""
Reviewer Agent (Architecture + Domain) — tenant-aware
----------------------------------------------------
Generates a concise review of the architecture blueprint and domain model.
Produces a Markdown artefact. **Does not** mark the task done — the user
must approve via the Reviews API to unblock downstream tasks.
"""
import logging
from typing import Optional

from .utils import load_template

from ai_org_backend.db import SessionLocal
from ai_org_backend.models import Purpose, Task
from ai_org_backend.services.storage import save_artefact
from ai_org_backend.services.llm_client import chat_with_tools, MODEL_PRO
from ai_org_backend.tasks.celery_app import celery

# Small metrics parity (keeps style with other agents)
from ai_org_backend.metrics import prom_counter, prom_hist

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
        return chat_with_tools(messages=messages, model=MODEL_PRO, temperature=0, tenant=tenant_id)
    except TypeError:
        # Fallback: older signature without 'tenant'
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
        ctx = {"purpose_name": purpose.name, "tenant_id": purpose.tenant_id, "blueprint": blueprint_md}
        prompt = PROMPT_TMPL.render(**ctx)
        start = time.time()
        try:
            resp = _call_llm([{"role": "user", "content": prompt}], tenant_id=purpose.tenant_id)
            REVIEW_RUNS.inc()
            if not resp:
                return "⚠️ Budget exhausted or LLM unavailable; unable to generate review."
            return resp["choices"][0]["message"]["content"]
        finally:
            REVIEW_LAT.observe(time.time() - start)


@celery.task(name="agent.reviewer")
def reviewer_task(tenant_id: str, purpose_id: str, blueprint_task_id: str, review_task_id: str) -> None:
    """
    Celery entrypoint — creates the Markdown review artefact for the given review task.
    Leaves the task in 'todo' (awaiting approval).
    """
    logging.info("[Reviewer] Generating review for purpose=%s (tenant=%s)", purpose_id, tenant_id)
    with SessionLocal() as s:
        # Fetch blueprint content from its artefact(s)
        # Simplicity: we read the latest blueprint artefact saved for blueprint task.
        from ai_org_backend.models import Artefact
        blueprint_text = ""
        try:
            # Most recent artefact for the blueprint task (markdown)
            art = (
                s.query(Artefact)
                .filter(Artefact.task_id == blueprint_task_id)
                .order_by(Artefact.created_at.desc())
                .first()
            )
            if art and art.blob:
                blueprint_text = art.blob.decode("utf-8", errors="ignore")
        except Exception as e:
            logging.error("[Reviewer] Failed to load blueprint artefact: %s", e)
            blueprint_text = ""

    review_md = run_reviewer(purpose_id, blueprint_text)

    # Persist the review artefact (keep task status todo; user will approve)
    save_artefact(
        review_task_id,
        review_md.encode("utf-8"),
        filename="reviews/architecture_domain_review.md",
        allow_overwrite=True,
    )
    logging.info("[Reviewer] Review artefact saved for task=%s", review_task_id)
