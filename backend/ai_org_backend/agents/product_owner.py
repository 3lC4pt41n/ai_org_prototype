from __future__ import annotations

import logging
import time

from sqlalchemy import desc
from sqlmodel import select

from ai_org_backend.db import SessionLocal
from ai_org_backend.metrics import prom_counter, prom_hist
from ai_org_backend.models import Artifact, Purpose
from ai_org_backend.models.chat import ChatRole
from ai_org_backend.services.budget import BudgetExceededError
from ai_org_backend.services.llm_client import MODEL_PRO, chat_with_tools
from ai_org_backend.services.storage import resolve_for_read

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


def run_requirements(purpose: Purpose) -> str:
    """Generate a detailed Product Requirements Document (PRD) for the given project purpose."""

    vision_md = ""
    with SessionLocal() as db:
        fresh_purpose = db.get(Purpose, purpose.id)
        if not fresh_purpose:
            logger.error("Purpose %s not found for run_requirements", purpose.id)
            return "⚠️ Purpose not found; cannot gather requirements."
        purpose_name = fresh_purpose.name
        tenant_id = fresh_purpose.tenant_id

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

    if vision_md:
        logger.info(
            "PRD agent using latest vision for purpose %s (chars=%d)",
            purpose.id,
            len(vision_md),
        )
    else:
        logger.info("PRD agent starting without vision context for purpose %s", purpose.id)

    ctx = {"purpose": purpose_name, "vision": vision_md}
    prompt = PROMPT_TMPL.render(**ctx)
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
