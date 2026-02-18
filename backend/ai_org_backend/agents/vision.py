from __future__ import annotations

import logging
import time

from sqlmodel import select

from ai_org_backend.db import SessionLocal
from ai_org_backend.metrics import prom_counter, prom_hist
from ai_org_backend.models import Artifact, Purpose, Task, TaskOwner
from ai_org_backend.models.chat import ChatRole
from ai_org_backend.repo import Repo
from ai_org_backend.services.budget import BudgetExceededError
from ai_org_backend.services.llm_client import MODEL_PRO, chat_with_tools
from ai_org_backend.services.storage import register_artefact
from ai_org_backend.tasks.celery_app import celery

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


@celery.task(name="agent.vision")
def vision_task(
    tenant_id: str,
    task_id: str,
    purpose_id: str | None = None,
) -> None:
    """Celery task: generates the vision document asynchronously."""

    if purpose_id is None:
        with SessionLocal() as db:
            t = db.get(Task, task_id)
            if t:
                purpose_id = t.purpose_id
    if purpose_id is None:
        logger.error("[Vision] Cannot determine purpose for task %s", task_id)
        return

    repo = Repo(tenant_id)
    try:
        repo.update(task_id, status="doing", owner=TaskOwner.VISION_AGENT, notes="Vision in progress")
    except Exception:
        logger.exception("[Vision] Failed to mark task %s as doing", task_id)

    with SessionLocal() as db:
        purpose = db.get(Purpose, purpose_id)
        if not purpose:
            logger.error("[Vision] Purpose %s not found", purpose_id)
            return

    try:
        vision_content = run_vision(purpose)
    except Exception as exc:
        logger.error("[Vision] Agent failed for purpose %s: %s", purpose_id, exc)
        try:
            repo.update(task_id, status="failed", owner=TaskOwner.VISION_AGENT, notes=f"Vision error: {exc}")
        except Exception:
            logger.exception("[Vision] Failed to record failure for task %s", task_id)
        return

    try:
        register_artefact(
            task_id,
            vision_content.encode("utf-8"),
            filename="vision/vision_statement.md",
            media_type="text/markdown",
        )
    except Exception as exc:
        logger.exception("[Vision] Failed to persist artefact for task %s: %s", task_id, exc)
        try:
            repo.update(task_id, status="failed", owner=TaskOwner.VISION_AGENT, notes=f"Vision save failed: {exc}")
        except Exception:
            pass
        return

    try:
        from ai_org_backend.services import budget as budget_svc
        budget_svc.debit(purpose_id=purpose_id, amount=max(1, len(vision_content) // 4), reason="artifact:vision")
    except Exception as exc:
        logger.warning("[Vision] Budget debit failed (non-fatal): %s", exc)

    try:
        repo.update(task_id, status="done", owner=TaskOwner.VISION_AGENT, notes="Vision completed")
    except Exception:
        logger.exception("[Vision] Failed to mark task %s as done", task_id)

    # In auto mode: auto-release the artefact
    with SessionLocal() as db:
        purpose = db.get(Purpose, purpose_id)
        if purpose and purpose.mode == "auto":
            art = db.exec(
                select(Artifact).where(Artifact.task_id == task_id)
            ).first()
            if art:
                art.released = True
                db.add(art)
                db.commit()
                logger.info("[Vision] Auto-released artefact %s for purpose %s", art.id, purpose_id)

    # In manual mode: set pause flag so user can review
    with SessionLocal() as db:
        purpose = db.get(Purpose, purpose_id)
        if purpose and purpose.mode == "manual":
            try:
                from ai_org_backend.redis_client import pool
                pool.set(f"pause:{tenant_id}:{purpose_id}", "1")
                logger.info("[Vision] Paused purpose %s (manual mode)", purpose_id)
            except Exception as exc:
                logger.error("[Vision] Failed to set pause flag: %s", exc)
