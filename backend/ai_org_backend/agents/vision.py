from __future__ import annotations

import logging
import time

from sqlmodel import select

from ai_org_backend.db import SessionLocal
from ai_org_backend.metrics import prom_counter, prom_hist
from ai_org_backend.models import Purpose, Task
from ai_org_backend.models.chat import ChatRole
from ai_org_backend.services.budget import BudgetExceededError
from ai_org_backend.services.llm_client import MODEL_PRO, chat_with_tools

from .utils import load_template

VISION_RUNS = prom_counter("ai_vision_runs_total", "Vision agent executions")
VISION_LATENCY = prom_hist("ai_vision_latency_seconds", "Vision agent latency")

PROMPT_TMPL = load_template("vision.j2")

logger = logging.getLogger(__name__)


def run_vision(purpose: Purpose) -> str:
    """Generate a high-level project vision for the given purpose."""

    template_key: str | None = None
    with SessionLocal() as db:
        fresh_purpose = db.get(Purpose, purpose.id)
        if not fresh_purpose:
            logger.error("Purpose %s not found for run_vision", purpose.id)
            return "⚠️ Purpose not found; cannot craft project vision."
        purpose_name = fresh_purpose.name
        tenant_id = fresh_purpose.tenant_id
        vision_task = db.exec(
            select(Task)
            .where(Task.purpose_id == purpose.id)
            .where(Task.description.ilike("vision document%"))
        ).first()
        if vision_task and vision_task.prompt_template:
            template_key = vision_task.prompt_template

    logger.info(
        "Vision agent starting for purpose %s (tenant=%s)", purpose.id, tenant_id
    )
    prompt_template = PROMPT_TMPL
    if template_key:
        try:
            prompt_template = load_template(template_key)
        except FileNotFoundError:
            logger.warning(
                "Custom vision prompt %s not found; falling back to default", template_key
            )
        except Exception:
            logger.exception("Failed to load custom vision prompt %s", template_key)
    prompt = prompt_template.render(purpose=purpose_name)
    start_time = time.time()
    try:
        resp = chat_with_tools(
            messages=[{"role": ChatRole.USER.value, "content": prompt}],
            model=MODEL_PRO,
            tenant_id=tenant_id,
            usage_label="vision",
        )
        VISION_RUNS.inc()
        content = resp["choices"][0]["message"]["content"]
        logger.info(
            "Vision agent succeeded for purpose %s (chars=%d)",
            purpose.id,
            len(content or ""),
        )
        return content
    except BudgetExceededError:
        logger.warning(
            "Vision agent budget exceeded for purpose %s", purpose.id
        )
        return "⚠️ Budget exhausted during vision drafting. Please top up and retry."
    except Exception:
        logger.exception("Vision agent failed for purpose %s", purpose.id)
        raise
    finally:
        VISION_LATENCY.observe(time.time() - start_time)
