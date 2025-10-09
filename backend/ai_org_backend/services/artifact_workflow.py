"""Shared helpers for artifact feedback and approval workflows."""

from __future__ import annotations

import json
import logging
from typing import Any, Iterable

from sqlalchemy import desc, select
from sqlmodel import Session

from ai_org_backend.agents.product_owner import run_requirements_feedback
from ai_org_backend.db import engine
from ai_org_backend.models import Artifact, Purpose, Task, TaskOwner
from ai_org_backend.models.chat import ChatIntent, ChatMessage, ChatMessageArtifact, ChatRole, ChatScope
from ai_org_backend.repo import Repo
from ai_org_backend.services import budget as budget_svc
from ai_org_backend.services.storage import register_artefact, resolve_for_read

logger = logging.getLogger(__name__)


def consistency_check(artifact: Artifact, session: Session) -> dict[str, Any] | None:
    """Return a follow-up recommendation for artifacts impacted by a feedback change."""

    impacted_ids: list[str] = []
    impact_level = "low"
    change_type = "informational"
    followup_suggestion: str | None = None
    task_desc = (artifact.task.description if artifact.task else "").lower()
    repo_path = (artifact.repo_path or "").lower()

    if "product requirements" in task_desc or "product_requirements" in repo_path:
        impact_level = "high"
        change_type = "followup_needed"
        arch_artifact = session.exec(
            select(Artifact)
            .where(Artifact.task.has(purpose_id=artifact.task.purpose_id))
            .where(Artifact.repo_path.ilike("%architecture_blueprint.md"))
            .order_by(desc(Artifact.created_at))
        ).first()
        if arch_artifact:
            impacted_ids.append(arch_artifact.id)
        test_artifact = session.exec(
            select(Artifact)
            .where(Artifact.task.has(purpose_id=artifact.task.purpose_id))
            .where(Artifact.repo_path.ilike("%test%"))
            .order_by(desc(Artifact.created_at))
        ).first()
        if test_artifact:
            impacted_ids.append(test_artifact.id)
        ui_artifact = session.exec(
            select(Artifact)
            .where(Artifact.task.has(purpose_id=artifact.task.purpose_id))
            .where(Artifact.repo_path.ilike("%ui%"))
            .order_by(desc(Artifact.created_at))
        ).first()
        if ui_artifact:
            impacted_ids.append(ui_artifact.id)
        followup_suggestion = "Update architecture" if arch_artifact else "Create architecture"
    elif "blueprint" in task_desc or "architecture_blueprint" in repo_path:
        impact_level = "medium"
        change_type = "followup_needed"
        test_artifact = session.exec(
            select(Artifact)
            .where(Artifact.task.has(purpose_id=artifact.task.purpose_id))
            .where(Artifact.repo_path.ilike("%test%"))
            .order_by(desc(Artifact.created_at))
        ).first()
        if test_artifact:
            impacted_ids.append(test_artifact.id)
        followup_suggestion = "Review test cases"
    elif "ui" in task_desc or "ui" in repo_path:
        impact_level = "medium"
        change_type = "informational"
        test_artifact = session.exec(
            select(Artifact)
            .where(Artifact.task.has(purpose_id=artifact.task.purpose_id))
            .where(Artifact.repo_path.ilike("%test%"))
            .order_by(desc(Artifact.created_at))
        ).first()
        if test_artifact:
            impacted_ids.append(test_artifact.id)
        followup_suggestion = "Update UI tests"
    elif "test" in task_desc or "test" in repo_path:
        impact_level = "low"
        change_type = "informational"
        followup_suggestion = "Code anpassen"
    else:
        return None

    return {
        "betroffene_artefakte": impacted_ids,
        "impact_level": impact_level,
        "change_type": change_type,
        "followup_suggestion": followup_suggestion,
    }


def integrate_prd_feedback(
    session: Session,
    *,
    artifact: Artifact,
    purpose: Purpose,
    tenant_id: str,
    feedback: str,
    link_to_artifacts: Iterable[str] | None = None,
    versions: dict[str, int] | None = None,
) -> ChatMessage | None:
    """Apply feedback to a PRD artifact and persist bookkeeping chat messages."""

    if not feedback:
        return

    current_prd = ""
    try:
        file_path = resolve_for_read(artifact.repo_path)
        current_prd = file_path.read_text(encoding="utf-8")
    except Exception as exc:  # pragma: no cover - logging only
        logger.warning("Failed to read existing PRD file: %s", exc)
        current_prd = ""

    try:
        updated_prd_md = run_requirements_feedback(
            purpose, feedback=feedback, current_prd=current_prd
        )
        register_artefact(
            artifact.task_id,
            updated_prd_md.encode("utf-8"),
            filename=artifact.repo_path,
            media_type=artifact.media_type,
            allow_overwrite=True,
        )
    except Exception as exc:  # pragma: no cover - logging only
        logger.error("PRD update failed: %s", exc)

    # Inform downstream artefact owners through an agent note
    consistency = consistency_check(artifact, session)
    if not consistency:
        return None

    metadata: dict[str, Any] = {"note": "feedback integrated"}
    if versions:
        metadata["artifact_versions"] = versions
        if len(versions) == 1:
            metadata["version"] = next(iter(versions.values()))

    agent_msg = ChatMessage(
        tenant_id=tenant_id,
        purpose_id=purpose.id,
        artifact_id=None,
        task_id=artifact.task_id,
        role=ChatRole.AGENT,
        scope=ChatScope.ARTIFACT,
        intent=ChatIntent.NOTE,
        content=json.dumps(consistency, ensure_ascii=False),
        metadata=metadata,
    )
    session.add(agent_msg)
    for aid in link_to_artifacts or []:
        session.add(ChatMessageArtifact(chat_message_id=agent_msg.id, artifact_id=aid))

    return agent_msg


def generate_prd_artifact(
    purpose: Purpose, existing_task: Task | None = None
) -> tuple[Task, str, Artifact | None]:
    """Create or refresh the PRD artifact for a purpose."""

    from ai_org_backend.agents.product_owner import run_requirements

    tenant_id = purpose.tenant_id
    logger.info(
        "Starting PRD artefact generation for purpose %s (mode=%s)",
        purpose.id,
        purpose.mode,
    )

    with Session(engine) as session:
        if existing_task:
            prd_task = session.get(Task, existing_task.id) or existing_task
        else:
            prd_task = Task(
                tenant_id=tenant_id,
                purpose_id=purpose.id,
                description="Product Requirements Document",
                business_value=0.0,
                tokens_plan=0,
                purpose_relevance=1.0,
            )
            session.add(prd_task)
            session.commit()
            session.refresh(prd_task)

    repo = Repo(tenant_id)
    try:
        prd_task = repo.update(
            prd_task.id,
            status="doing",
            owner=TaskOwner.PRODUCT_OWNER,
            notes="PRD in progress",
        )
    except Exception:  # pragma: no cover - bookkeeping only
        logger.exception("Failed to mark PRD task %s as in progress", prd_task.id)

    prd_content = ""
    try:
        prd_content = run_requirements(purpose)
    except Exception as exc:
        logger.error("PRD agent failed for purpose %s: %s", purpose.id, exc)
        try:
            repo.update(
                prd_task.id,
                status="failed",
                owner=TaskOwner.PRODUCT_OWNER,
                notes=f"PRD agent error: {exc}",
            )
        except Exception:  # pragma: no cover - bookkeeping only
            logger.exception(
                "Failed to record PRD task failure for task %s", prd_task.id
            )
        raise

    artifact: Artifact | None = None
    repo_rel = "requirements/product_requirements_document.md"
    try:
        artifact = register_artefact(
            prd_task.id,
            prd_content.encode("utf-8"),
            filename=repo_rel,
            media_type="text/markdown",
            allow_overwrite=True,
        )
        logger.info(
            "PRD artefact %s stored for purpose %s (path=%s)",
            artifact.id,
            purpose.id,
            artifact.repo_path,
        )
    except Exception as exc:
        logger.exception(
            "failed to persist artefact to workspace (%s): %s",
            repo_rel,
            exc,
        )
        try:
            repo.update(
                prd_task.id,
                status="failed",
                owner=TaskOwner.PRODUCT_OWNER,
                notes=f"PRD save failed: {exc}",
            )
        except Exception:  # pragma: no cover - bookkeeping only
            logger.exception(
                "Failed to record PRD save error for task %s", prd_task.id
            )
        raise

    try:
        token_guess = max(1, len(prd_content) // 4)
        budget_svc.debit(
            purpose_id=purpose.id,
            amount=token_guess,
            reason="artifact:requirements",
        )
    except Exception as exc:  # pragma: no cover - bookkeeping only
        logger.warning("budget debit failed (non-fatal): %s", exc)

    try:
        repo.update(
            prd_task.id,
            status="done",
            owner=TaskOwner.PRODUCT_OWNER,
            notes="PRD ready",
        )
    except Exception:  # pragma: no cover - bookkeeping only
        logger.exception("Failed to mark PRD task %s as done", prd_task.id)

    return prd_task, prd_content, artifact
