from __future__ import annotations

import logging
import time

from sqlalchemy import desc
from sqlmodel import select

from ai_org_backend.db import SessionLocal
from ai_org_backend.main import (
    TOKEN_PRICE_PER_1000,
    Repo,
    TASK_CNT,
    TASK_LAT,
    debit,
)
from ai_org_backend.metrics import prom_counter, prom_hist
from ai_org_backend.models import Artifact, Purpose, Task, TaskOwner
from ai_org_backend.models.chat import ChatRole
from ai_org_backend.services.budget import BudgetExceededError
from ai_org_backend.services.llm_client import MODEL_PRO, chat_with_tools
from ai_org_backend.services.storage import resolve_for_read, save_artefact
from ai_org_backend.tasks.celery_app import celery

from .utils import load_template

PRODUCT_REQ_RUNS = prom_counter(
    "ai_product_requirements_runs_total", "Product Requirements agent executions"
)
PRODUCT_REQ_LATENCY = prom_hist(
    "ai_product_requirements_latency_seconds", "Product Requirements agent latency"
)

PROMPT_TMPL = load_template("requirements.j2")
PROMPT_FEEDBACK_TMPL = load_template("requirements_feedback.j2")

logger = logging.getLogger(__name__)


def _prepare_prd_prompt(purpose: Purpose) -> tuple[str | None, str | None, str]:
    """Return tenant, rendered prompt and vision context for a purpose."""

    vision_md = ""
    template_key: str | None = None
    purpose_name = ""
    tenant_id: str | None = None
    vision_art: Artifact | None = None
    with SessionLocal() as db:
        fresh_purpose = db.get(Purpose, purpose.id)
        if not fresh_purpose:
            logger.error("Purpose %s not found for PRD preparation", purpose.id)
            return None, None, vision_md
        purpose_name = fresh_purpose.name
        tenant_id = fresh_purpose.tenant_id

        prd_task = db.exec(
            select(Task)
            .where(Task.purpose_id == fresh_purpose.id)
            .where(Task.description.ilike("product requirements document%"))
        ).first()
        if prd_task and prd_task.prompt_template:
            template_key = prd_task.prompt_template

        try:
            vision_art = db.exec(
                select(Artifact)
                .where(
                    Artifact.task.has(
                        purpose_id=fresh_purpose.id, tenant_id=fresh_purpose.tenant_id
                    )
                )
                .where(Artifact.repo_path.ilike("%vision%"))
                .order_by(desc(Artifact.created_at))
            ).first()
        except Exception as exc:
            logger.warning("Failed to load vision artifact metadata: %s", exc)
            vision_art = None

    if vision_art:
        try:
            file_path = resolve_for_read(vision_art.repo_path)
            vision_md = file_path.read_text(encoding="utf-8")
        except Exception as exc:
            logger.warning("Failed to read vision artefact %s: %s", vision_art.id, exc)

    prompt_template = PROMPT_TMPL
    if template_key:
        try:
            prompt_template = load_template(template_key)
        except FileNotFoundError:
            logger.warning("Custom PRD prompt %s not found; using default", template_key)
        except Exception:
            logger.exception("Failed to load custom PRD prompt %s", template_key)

    ctx = {"purpose": purpose_name, "vision": vision_md}
    prompt = prompt_template.render(**ctx)
    return tenant_id, prompt, vision_md


def run_requirements(purpose: Purpose) -> str:
    """Generate a detailed Product Requirements Document (PRD) for the given project purpose."""

    tenant_id, prompt, vision_md = _prepare_prd_prompt(purpose)
    if tenant_id is None or prompt is None:
        return "⚠️ Purpose not found; cannot gather requirements."

    if vision_md:
        logger.info(
            "PRD agent using latest vision for purpose %s (chars=%d)",
            purpose.id,
            len(vision_md),
        )
    else:
        logger.info("PRD agent starting without vision context for purpose %s", purpose.id)

    start_time = time.time()
    try:
        resp = chat_with_tools(
            messages=[{"role": ChatRole.USER.value, "content": prompt}],
            model=MODEL_PRO,
            tenant_id=tenant_id,
            usage_label="requirements",
        )
        PRODUCT_REQ_RUNS.inc()
        content = resp["choices"][0]["message"]["content"]
        logger.info(
            "PRD agent succeeded for purpose %s (chars=%d)",
            purpose.id,
            len(content or ""),
        )
        return content
    except BudgetExceededError:
        logger.warning(
            "PRD agent budget exceeded for purpose %s", purpose.id
        )
        return "⚠️ Budget exhausted during requirements gathering. Please top up and retry."
    except Exception:
        logger.exception("PRD agent failed for purpose %s", purpose.id)
        raise
    finally:
        PRODUCT_REQ_LATENCY.observe(time.time() - start_time)


def run_requirements_feedback(purpose: Purpose, feedback: str, current_prd: str) -> str:
    """Update existing PRD based on user feedback."""

    with SessionLocal() as db:
        fresh_purpose = db.get(Purpose, purpose.id)
        if not fresh_purpose:
            logger.error(
                "Purpose %s not found for run_requirements_feedback", purpose.id
            )
            return "⚠️ Purpose not found; cannot update requirements."
        purpose_name = fresh_purpose.name
        tenant_id = fresh_purpose.tenant_id

    ctx = {"purpose": purpose_name, "feedback": feedback, "current_prd": current_prd}
    prompt = PROMPT_FEEDBACK_TMPL.render(**ctx)
    start_time = time.time()
    try:
        resp = chat_with_tools(
            messages=[{"role": ChatRole.USER.value, "content": prompt}],
            model=MODEL_PRO,
            tenant_id=tenant_id,
            usage_label="requirements_feedback",
        )
        PRODUCT_REQ_RUNS.inc()
        content = resp["choices"][0]["message"]["content"]
        return content
    except BudgetExceededError:
        return "⚠️ Budget exhausted during requirements update. Please top up and retry."
    finally:
        PRODUCT_REQ_LATENCY.observe(time.time() - start_time)


@celery.task(name="agent.po")
def agent_po(tenant_id: str, task_id: str) -> None:
    """Generate and persist a PRD for the given task using the LLM."""

    logging.info("[ProductOwner] Starting PRD for Task %s (tenant %s)", task_id, tenant_id)
    with TASK_LAT.labels("po", tenant_id).time():
        with SessionLocal() as session:
            task = session.get(Task, task_id)
            if not task:
                logging.error("[ProductOwner] Task %s not found", task_id)
                return
            purpose = session.get(Purpose, task.purpose_id)
            if not purpose:
                logging.error("[ProductOwner] Purpose not found for task %s", task_id)
                return
            tenant_for_prompt, prompt, _ = _prepare_prd_prompt(purpose)
            purpose_id = purpose.id

        if tenant_for_prompt is None or prompt is None:
            Repo(tenant_id).update(
                task_id,
                status="failed",
                owner=TaskOwner.PRODUCT_OWNER.value,
                notes="Purpose not found for PRD generation",
            )
            return

        try:
            resp = chat_with_tools(
                messages=[{"role": ChatRole.USER.value, "content": prompt}],
                model=MODEL_PRO,
                tenant_id=tenant_id,
                usage_label="requirements",
            )
            content = (
                resp.choices[0].message.content
                if hasattr(resp, "choices")
                else resp["choices"][0]["message"]["content"]
            )
        except Exception as exc:
            logging.error("[ProductOwner] LLM failed: %s", exc)
            Repo(tenant_id).update(
                task_id,
                status="failed",
                owner=TaskOwner.PRODUCT_OWNER.value,
                notes=str(exc),
            )
            return

        save_artefact(
            task_id,
            (content or "").encode("utf-8"),
            filename="requirements/product_requirements.md",
            media_type="text/markdown",
            allow_overwrite=True,
        )

        tokens_used = 0
        usage = getattr(resp, "usage", None)
        if isinstance(usage, dict):
            tokens_used = usage.get("total_tokens", 0)
        elif hasattr(usage, "total_tokens"):
            tokens_used = getattr(usage, "total_tokens", 0)

        Repo(tenant_id).update(
            task_id,
            status="done",
            owner=TaskOwner.PRODUCT_OWNER.value,
            notes="PRD completed",
            tokens_actual=tokens_used,
        )
        try:
            debit(
                tenant_id,
                tokens_used * (TOKEN_PRICE_PER_1000 / 1000.0),
                purpose_id,
            )
        except Exception as exc:  # pragma: no cover - best effort billing
            logging.warning("[ProductOwner] Debit failed: %s", exc)
        TASK_CNT.labels(tenant_id, "po", "done").inc()
