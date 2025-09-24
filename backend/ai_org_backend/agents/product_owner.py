"""Agents responsible for creating and updating the Product Requirements Document."""

from __future__ import annotations

import logging
from typing import Tuple

from sqlalchemy import desc, func
from sqlmodel import Session, select

from ai_org_backend.db import SessionLocal, engine
from ai_org_backend.models import Artifact, Purpose, Task
from ai_org_backend.models.chat import ChatRole
from ai_org_backend.services.budget import BudgetExceededError
from ai_org_backend.services.llm_client import MODEL_PRO, chat_with_tools
from ai_org_backend.services.storage import resolve_for_read, save_artefact
from ai_org_backend.tasks.celery_app import celery
from ai_org_backend.metrics import TASK_CNT, TASK_LAT
from ai_org_backend.services.repo import Repo, debit
from ai_org_backend.settings import settings

from .utils import load_template

PROMPT_TMPL = load_template("requirements.j2")
PROMPT_FEEDBACK_TMPL = load_template("requirements_feedback.j2")

logger = logging.getLogger(__name__)


def _extract_usage(resp: object) -> int:
    """Best-effort extraction of total token usage from an OpenAI response."""

    usage = getattr(resp, "usage", None)
    if hasattr(usage, "total_tokens"):
        try:
            return int(getattr(usage, "total_tokens") or 0)
        except Exception:  # pragma: no cover - defensive fallback
            return 0
    if isinstance(usage, dict):
        return int(usage.get("total_tokens", 0) or 0)
    if isinstance(resp, dict):
        usage_dict = resp.get("usage", {})  # type: ignore[arg-type]
        if isinstance(usage_dict, dict):
            return int(usage_dict.get("total_tokens", 0) or 0)
    return 0


def _extract_content(resp: object) -> str:
    """Return the assistant message content from a chat completion response."""

    if hasattr(resp, "choices"):
        choices = getattr(resp, "choices")
        if choices:
            message = getattr(choices[0], "message", None)
            if message is not None:
                return getattr(message, "content", "") or ""
    if isinstance(resp, dict):
        try:
            return resp["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):  # pragma: no cover - best effort
            return ""
    return ""


def _load_latest_vision(purpose: Purpose) -> str:
    """Fetch the most recent vision artefact content for the given purpose."""

    with Session(engine) as session:
        vision_artifact = session.exec(
            select(Artifact)
            .join(Task, Task.id == Artifact.task_id)
            .where(Task.purpose_id == purpose.id)
            .where(func.lower(Task.description) == "vision document")
            .order_by(desc(Artifact.created_at))
        ).first()

    if not vision_artifact:
        return ""
    try:
        file_path = resolve_for_read(vision_artifact.repo_path)
        return file_path.read_text(encoding="utf-8")
    except Exception as exc:  # pragma: no cover - filesystem failures are best-effort
        logger.warning(
            "[ProductOwner] Failed to read vision artefact %s for purpose %s: %s",
            vision_artifact.id,
            purpose.id,
            exc,
        )
        return ""


def _render_prd_prompt(purpose: Purpose, vision: str) -> str:
    ctx = {"purpose": purpose.name, "vision": vision or ""}
    return PROMPT_TMPL.render(**ctx)


def _call_llm(prompt: str, tenant_id: str, usage_label: str | None = None) -> Tuple[str, int]:
    resp = chat_with_tools(
        messages=[{"role": ChatRole.USER.value, "content": prompt}],
        model=MODEL_PRO,
        tenant_id=tenant_id,
        usage_label=usage_label,
    )
    content = _extract_content(resp)
    tokens_used = _extract_usage(resp)
    logger.debug(
        "[ProductOwner] LLM returned %d chars (tokens=%d) for tenant %s",
        len(content),
        tokens_used,
        tenant_id,
    )
    return content, tokens_used


def generate_prd(purpose: Purpose, vision: str | None = None) -> Tuple[str, int]:
    """Generate PRD markdown and token usage for the provided purpose."""

    vision_md = vision if vision is not None else _load_latest_vision(purpose)
    prompt = _render_prd_prompt(purpose, vision_md)
    return _call_llm(prompt, tenant_id=purpose.tenant_id, usage_label="requirements")


def run_requirements(purpose: Purpose) -> str:
    """Backwards-compatible helper used by seeding and legacy flows."""

    try:
        content, _ = generate_prd(purpose)
        return content
    except BudgetExceededError:
        logger.warning(
            "[ProductOwner] Budget exceeded while generating PRD for purpose %s",
            purpose.id,
        )
        return "⚠️ Budget exhausted during requirements gathering. Please top up and retry."


def run_requirements_feedback(purpose: Purpose, feedback: str, current_prd: str) -> str:
    """Update existing PRD based on user feedback."""

    prompt = PROMPT_FEEDBACK_TMPL.render(
        purpose=purpose.name, feedback=feedback, current_prd=current_prd
    )
    try:
        content, _ = _call_llm(
            prompt, tenant_id=purpose.tenant_id, usage_label="requirements_feedback"
        )
        return content
    except BudgetExceededError:
        logger.warning(
            "[ProductOwner] Budget exceeded during PRD feedback for purpose %s",
            purpose.id,
        )
        return "⚠️ Budget exhausted during requirements update. Please top up and retry."


@celery.task(name="agent.po")
def agent_po(tenant_id: str, task_id: str) -> None:
    """Celery task that generates a PRD and persists it as an artefact."""

    logger.info("[ProductOwner] Starting PRD for Task %s (tenant %s)", task_id, tenant_id)
    with TASK_LAT.labels("po", tenant_id).time():
        with SessionLocal() as session:
            task = session.get(Task, task_id)
            if not task:
                logger.error("[ProductOwner] Task %s not found", task_id)
                return

            purpose = session.get(Purpose, task.purpose_id)
            if not purpose:
                logger.error(
                    "[ProductOwner] Purpose not found for task %s (purpose_id=%s)",
                    task_id,
                    task.purpose_id,
                )
                return

        vision_md = task.notes or ""
        if not vision_md:
            vision_md = _load_latest_vision(purpose)

        try:
            content, tokens_used = generate_prd(purpose, vision_md)
        except Exception as exc:  # pragma: no cover - failures handled via Repo update
            logger.error("[ProductOwner] LLM failed for task %s: %s", task_id, exc)
            Repo(tenant_id).update(
                task_id,
                status="failed",
                owner="PO",
                notes=str(exc),
            )
            return

        try:
            save_artefact(
                task_id,
                content.encode("utf-8"),
                filename="requirements/product_requirements.md",
                media_type="text/markdown",
                allow_overwrite=True,
            )
        except Exception as exc:  # pragma: no cover - storage failures should be surfaced
            logger.error(
                "[ProductOwner] Failed to save PRD artefact for task %s: %s",
                task_id,
                exc,
            )
            Repo(tenant_id).update(
                task_id,
                status="failed",
                owner="PO",
                notes=f"artefact save failed: {exc}",
            )
            return

        Repo(tenant_id).update(
            task_id,
            status="done",
            owner="PO",
            notes="PRD completed",
            tokens_actual=tokens_used,
        )

        try:
            debit(
                tenant_id,
                tokens_used * (settings.token_price_per_1000 / 1000.0),
                purpose.id,
            )
        except Exception as exc:  # pragma: no cover - billing is best-effort
            logger.warning("[ProductOwner] Debit failed for task %s: %s", task_id, exc)

        TASK_CNT.labels(tenant_id, "po", "done").inc()
