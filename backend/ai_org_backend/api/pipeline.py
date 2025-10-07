import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import asc, desc, exists, or_
from sqlalchemy.orm import selectinload
from sqlmodel import Session, select

from ai_org_backend.api.dependencies import get_current_tenant, get_session
from ai_org_backend.db import engine
from ai_org_backend.models import (
    Artifact,
    PromptTemplate,
    Purpose,
    Task,
    TaskDependency,
    TaskOwner,
    Tenant,
    TenantPromptAssignment,
)
from ai_org_backend.models.chat import (
    ChatIntent,
    ChatMessage,
    ChatMessageArtifact,
    ChatRole,
    ChatScope,
)
from ai_org_backend.redis_client import DEFAULT_BUDGET, pool
from ai_org_backend.repo import Repo
from ai_org_backend.services import budget as budget_svc
from ai_org_backend.services.pipeline_templates import (
    ensure_template_for_purpose,
    instantiate_pipeline_for_purpose,
    list_templates_for_tenant,
    resolve_pipeline_template,
    template_to_dict,
    update_phase_configuration,
)
from ai_org_backend.services.storage import (
    WORKSPACE,
    resolve_for_read,
    register_artefact,
    vector_store,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["pipeline"])


_SYSTEM_PROMPT_LABELS = {
    "vision": "Vision Document",
    "requirements": "Product Requirements Document",
    "architect": "Architecture Blueprint",
    "architect_feedback": "Architecture Blueprint Update",
    "review": "Architecture & Domain Review",
    "planner": "Implementation Plan",
}


def _clean_template_name(value: str | None) -> str | None:
    if not value:
        return None
    candidate = Path(value).name
    if candidate.lower().endswith(".j2"):
        candidate = candidate[:-3]
    return candidate or None


def _derive_template_name(template: PromptTemplate) -> str:
    default_name = _clean_template_name(template.default_path)
    if default_name:
        mapped = _SYSTEM_PROMPT_LABELS.get(default_name.lower())
        return mapped or default_name
    if template.created_by is None:
        fallback = _SYSTEM_PROMPT_LABELS.get(template.phase_slug.lower())
        if fallback:
            return fallback
        return template.phase_slug.replace("_", " ").title()
    return template.id


def _template_owned_by(template: PromptTemplate, tenant_id: str) -> bool:
    """Return True if the template belongs to the provided tenant."""

    if not tenant_id:
        return False
    assignments = getattr(template, "assignments", []) or []
    return bool(
        (template.created_by == tenant_id)
        or any(assignment.tenant_id == tenant_id for assignment in assignments)
    )


def _template_accessible(template: PromptTemplate, tenant_id: str) -> bool:
    """Return True if the template can be read/modified by the tenant."""

    return bool(
        template.created_by is None
        or _template_owned_by(template, tenant_id)
    )


def _normalize_agent(agent: str | None) -> str | None:
    """Return a stripped agent identifier or ``None`` for empty values."""

    if agent is None:
        return None
    normalized = agent.strip()
    return normalized or None


def _agent_match_clause(agent: str | None):
    """Return a SQLAlchemy clause that matches the provided agent value."""

    normalized = _normalize_agent(agent)
    if normalized is None:
        return or_(
            TenantPromptAssignment.agent.is_(None),
            TenantPromptAssignment.agent == "",
        )
    return TenantPromptAssignment.agent == normalized


def _normalize_prompt_content(content: Any) -> str:
    """Ensure prompt content is returned as a plain string."""

    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, dict) and "content" in content:
        value = content.get("content")
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        return str(value)
    return str(content)


@router.get("/pipeline/templates", tags=["pipeline"])
def list_pipeline_templates_endpoint(
    current_tenant: Tenant = Depends(get_current_tenant),
):
    with Session(engine) as session:
        templates = list_templates_for_tenant(session, current_tenant.id)
        return [template_to_dict(template) for template in templates]


@router.get("/pipeline/prompts", tags=["pipeline"])
def list_prompt_templates_endpoint(
    current_tenant: Tenant = Depends(get_current_tenant),
):
    with Session(engine) as session:
        templates = session.exec(
            select(PromptTemplate)
            .options(selectinload(PromptTemplate.assignments))
            .where(
                or_(
                    PromptTemplate.created_by.is_(None),
                    PromptTemplate.created_by == current_tenant.id,
                    exists()
                    .where(
                        TenantPromptAssignment.tenant_id == current_tenant.id,
                        TenantPromptAssignment.prompt_template_id == PromptTemplate.id,
                    )
                    .correlate(PromptTemplate),
                )
            )
            .order_by(PromptTemplate.phase_slug, PromptTemplate.created_at)
        ).unique().all()
        assignments = session.exec(
            select(TenantPromptAssignment).where(
                TenantPromptAssignment.tenant_id == current_tenant.id
            )
        ).all()

    assignment_by_key = {
        (
            assignment.phase_slug,
            _normalize_agent(getattr(assignment, "agent", None)),
        ): assignment
        for assignment in assignments
    }

    template_payload = []
    for template in templates:
        key = (
            template.phase_slug,
            _normalize_agent(getattr(template, "agent", None)),
        )
        assignment = assignment_by_key.get(key)
        is_default = bool(
            assignment and assignment.prompt_template_id == template.id
        )
        tenant_specific = _template_owned_by(template, current_tenant.id)
        template_payload.append(
            {
                "id": template.id,
                "phase_slug": template.phase_slug,
                "agent": _normalize_agent(getattr(template, "agent", None)),
                "default_path": template.default_path,
                "content": _normalize_prompt_content(getattr(template, "content", None)),
                "tenant_id": current_tenant.id if tenant_specific else None,
                "created_by": template.created_by,
                "created_at": template.created_at.isoformat()
                if template.created_at
                else None,
                "updated_at": template.updated_at.isoformat()
                if template.updated_at
                else None,
                "is_tenant_default": is_default,
                "assignment_id": assignment.id if is_default else None,
                "name": _derive_template_name(template),
                "is_system": not tenant_specific,
            }
        )

    assignments_payload = [
        {
            "id": assignment.id,
            "phase_slug": assignment.phase_slug,
            "agent": _normalize_agent(getattr(assignment, "agent", None)),
            "prompt_template_id": assignment.prompt_template_id,
            "created_at": assignment.created_at.isoformat()
            if assignment.created_at
            else None,
        }
        for assignment in assignments
    ]

    return {"templates": template_payload, "assignments": assignments_payload}


@router.post("/pipeline/prompts/create", tags=["pipeline"])
def create_prompt_template(
    payload: dict, current_tenant: Tenant = Depends(get_current_tenant)
):
    phase_slug = (payload.get("phase_slug") or "").strip()
    if not phase_slug:
        raise HTTPException(status_code=400, detail="phase_slug is required")

    content = _normalize_prompt_content(payload.get("content"))
    agent_raw = payload.get("agent")
    agent = (
        _normalize_agent(str(agent_raw)) if agent_raw is not None else None
    )
    set_default = bool(payload.get("set_default"))
    purpose_id = payload.get("purpose_id")

    with Session(engine) as session:
        created_by_value = payload.get("created_by")
        created_by = (
            str(created_by_value).strip() if created_by_value else current_tenant.id
        )
        raw_default_path = payload.get("default_path")
        default_path = None
        if raw_default_path is not None:
            candidate = str(raw_default_path).strip()
            if candidate:
                default_path = candidate
        template = PromptTemplate(
            phase_slug=phase_slug,
            agent=agent,
            default_path=default_path,
            created_by=created_by,
            content=content,
        )
        session.add(template)
        session.commit()
        session.refresh(template)

        assignment_record: TenantPromptAssignment | None = None
        if set_default:
            assignment_record = session.exec(
                select(TenantPromptAssignment).where(
                    TenantPromptAssignment.tenant_id == current_tenant.id,
                    TenantPromptAssignment.phase_slug == phase_slug,
                    _agent_match_clause(agent),
                )
            ).first()
            if assignment_record:
                assignment_record.prompt_template_id = template.id
                assignment_record.agent = agent
            else:
                assignment_record = TenantPromptAssignment(
                    tenant_id=current_tenant.id,
                    phase_slug=phase_slug,
                    agent=agent,
                    prompt_template_id=template.id,
                )
            session.add(assignment_record)
            session.commit()
            session.refresh(assignment_record)

        purpose: Purpose | None = None
        if purpose_id:
            purpose = session.exec(
                select(Purpose).where(
                    Purpose.id == purpose_id,
                    Purpose.tenant_id == current_tenant.id,
                )
            ).first()
        if purpose and set_default:
            template_for_purpose = ensure_template_for_purpose(session, purpose)
            instantiate_pipeline_for_purpose(purpose, template_for_purpose)

        response = {
            "id": template.id,
            "prompt_template": {
                "id": template.id,
                "phase_slug": template.phase_slug,
                "agent": _normalize_agent(getattr(template, "agent", None)),
                "default_path": template.default_path,
                "content": _normalize_prompt_content(getattr(template, "content", None)),
                "tenant_id": current_tenant.id
                if _template_owned_by(template, current_tenant.id)
                else None,
                "created_by": template.created_by,
                "created_at": template.created_at.isoformat()
                if template.created_at
                else None,
                "updated_at": template.updated_at.isoformat()
                if template.updated_at
                else None,
                "name": _derive_template_name(template),
                "is_system": _template_owned_by(template, current_tenant.id) is False,
            },
        }
        if assignment_record:
            response["assignment"] = {
                "id": assignment_record.id,
                "phase_slug": assignment_record.phase_slug,
                "agent": _normalize_agent(getattr(assignment_record, "agent", None)),
                "prompt_template_id": assignment_record.prompt_template_id,
                "created_at": assignment_record.created_at.isoformat()
                if assignment_record.created_at
                else None,
            }
        return response


@router.put("/pipeline/prompts/update/{template_id}", tags=["pipeline"])
def update_prompt_template(
    template_id: str, payload: dict, current_tenant: Tenant = Depends(get_current_tenant)
):
    content = _normalize_prompt_content(payload.get("content"))
    with Session(engine) as session:
        template = session.exec(
            select(PromptTemplate)
            .options(selectinload(PromptTemplate.assignments))
            .where(PromptTemplate.id == template_id)
        ).first()
        if not template:
            raise HTTPException(status_code=404, detail="Prompt template not found")
        if not _template_accessible(template, current_tenant.id):
            raise HTTPException(status_code=403, detail="Forbidden for this template")

        template.content = content
        if "default_path" in payload:
            raw_name = payload.get("default_path")
            template.default_path = (str(raw_name).strip() or None) if raw_name is not None else None
        template.updated_at = datetime.utcnow()
        session.add(template)
        session.commit()
        session.refresh(template)
        return {"id": template.id}


@router.post("/pipeline/prompts/assign", tags=["pipeline"])
def assign_prompt_template(
    payload: dict, current_tenant: Tenant = Depends(get_current_tenant)
):
    phase_slug = (payload.get("phase_slug") or "").strip()
    template_id = payload.get("prompt_template_id")
    agent_raw = payload.get("agent")
    purpose_id = payload.get("purpose_id")

    if not phase_slug:
        raise HTTPException(status_code=400, detail="phase_slug is required")

    agent_value = (
        _normalize_agent(str(agent_raw)) if agent_raw is not None else None
    )

    if template_id in (None, ""):
        # Unassign prompt template for this phase/agent if exists
        with Session(engine) as session:
            assignment = session.exec(
                select(TenantPromptAssignment).where(
                    TenantPromptAssignment.tenant_id == current_tenant.id,
                    TenantPromptAssignment.phase_slug == phase_slug,
                    _agent_match_clause(agent_value),
                )
            ).first()
            if assignment:
                session.delete(assignment)
                session.commit()
        return {"assigned": True}

    with Session(engine) as session:
        template = session.exec(
            select(PromptTemplate)
            .options(selectinload(PromptTemplate.assignments))
            .where(PromptTemplate.id == template_id)
        ).first()
        if not template:
            raise HTTPException(status_code=404, detail="Prompt template not found")
        if not _template_accessible(template, current_tenant.id):
            raise HTTPException(status_code=403, detail="Forbidden for this template")

        assignment = session.exec(
            select(TenantPromptAssignment).where(
                TenantPromptAssignment.tenant_id == current_tenant.id,
                TenantPromptAssignment.phase_slug == phase_slug,
                _agent_match_clause(agent_value),
            )
        ).first()
        if assignment:
            assignment.prompt_template_id = template.id
            assignment.agent = agent_value
        else:
            assignment = TenantPromptAssignment(
                tenant_id=current_tenant.id,
                phase_slug=phase_slug,
                agent=agent_value,
                prompt_template_id=template.id,
            )
        session.add(assignment)
        session.commit()

        purpose: Purpose | None = None
        if purpose_id:
            purpose = session.exec(
                select(Purpose).where(
                    Purpose.id == purpose_id,
                    Purpose.tenant_id == current_tenant.id,
                )
            ).first()
        if purpose:
            template_for_purpose = ensure_template_for_purpose(session, purpose)
            instantiate_pipeline_for_purpose(purpose, template_for_purpose)

    return {"assigned": True}


def _latest_artifact_for_task(task_id: str | None) -> Artifact | None:
    if not task_id:
        return None
    with Session(engine) as session:
        return session.exec(
            select(Artifact)
            .where(Artifact.task_id == task_id)
            .order_by(desc(Artifact.created_at))
        ).first()


def _read_artifact_text(artifact: Artifact | None) -> str:
    if not artifact:
        return ""
    try:
        file_path = resolve_for_read(artifact.repo_path)
        return file_path.read_text(encoding="utf-8")
    except Exception as exc:
        logger.warning("Failed to read artefact %s: %s", artifact.id, exc)
        return ""


def _generate_vision_artifact(
    purpose: Purpose, existing_task: Task | None = None
) -> tuple[Task, str, Artifact | None]:
    from ai_org_backend.agents.vision import run_vision

    tenant_id = purpose.tenant_id
    logger.info(
        "Starting vision artefact generation for purpose %s (mode=%s)",
        purpose.id,
        purpose.mode,
    )

    with Session(engine) as session:
        if existing_task:
            vision_task = session.get(Task, existing_task.id) or existing_task
        else:
            vision_task = Task(
                tenant_id=tenant_id,
                purpose_id=purpose.id,
                description="Vision Document",
                business_value=0.0,
                tokens_plan=0,
                purpose_relevance=1.0,
            )
            session.add(vision_task)
            session.commit()
            session.refresh(vision_task)

    repo = Repo(tenant_id)
    try:
        vision_task = repo.update(
            vision_task.id,
            status="doing",
            owner=TaskOwner.VISION_AGENT,
            notes="Vision in progress",
        )
    except Exception:
        logger.exception("Failed to mark vision task %s as in progress", vision_task.id)
    vision_content = ""
    try:
        vision_content = run_vision(purpose)
    except Exception as exc:
        logger.error(
            "Vision agent failed for purpose %s: %s", purpose.id, exc
        )
        try:
            repo.update(
                vision_task.id,
                status="failed",
                owner=TaskOwner.VISION_AGENT,
                notes=f"Vision agent error: {exc}",
            )
        except Exception:
            logger.exception(
                "Failed to record vision task failure for task %s", vision_task.id
            )
        raise

    artifact: Artifact | None = None
    repo_rel = "vision/vision_statement.md"
    try:
        artifact = register_artefact(
            vision_task.id,
            vision_content.encode("utf-8"),
            filename=repo_rel,
            media_type="text/markdown",
        )
        logger.info(
            "Vision artefact %s stored for purpose %s (path=%s)",
            artifact.id,
            purpose.id,
            artifact.repo_path,
        )
    except Exception as exc:
        logger.exception(
            "failed to persist vision artefact to workspace (%s): %s",
            repo_rel,
            exc,
        )
        try:
            repo.update(
                vision_task.id,
                status="failed",
                owner=TaskOwner.VISION_AGENT,
                notes=f"Vision save failed: {exc}",
            )
        except Exception:
            logger.exception(
                "Failed to record vision save error for task %s", vision_task.id
            )
        raise

    try:
        token_guess = max(1, len(vision_content) // 4)
        budget_svc.debit(
            purpose_id=purpose.id,
            amount=token_guess,
            reason="artifact:vision",
        )
    except Exception as exc:
        logger.warning("budget debit for vision failed (non-fatal): %s", exc)

    try:
        repo.update(
            vision_task.id,
            status="done",
            owner=TaskOwner.VISION_AGENT,
            notes="Vision completed",
        )
    except Exception:
        logger.exception(
            "Failed to update vision task %s to done", vision_task.id
        )

    if purpose.mode == "auto" and artifact:
        released = False
        release_error = False
        try:
            with Session(engine) as session:
                art = session.get(Artifact, artifact.id)
                if art:
                    art.released = True
                    session.add(art)
                    session.commit()
                    released = True
                    artifact.released = True
        except Exception:
            release_error = True
            logger.exception(
                "Auto-release of vision artefact %s failed for purpose %s",
                artifact.id,
                purpose.id,
            )
        if released:
            logger.info(
                "Auto-released vision artefact %s for purpose %s", artifact.id, purpose.id
            )
        elif not release_error:
            logger.warning(
                "Vision artefact %s for purpose %s not auto-released", artifact.id, purpose.id
            )

    return vision_task, vision_content, artifact


def _generate_prd_artifact(
    purpose: Purpose, existing_task: Task | None = None
) -> tuple[Task, str, Artifact | None]:
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
    except Exception:
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
        except Exception:
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
        except Exception:
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
    except Exception as exc:
        logger.warning("budget debit failed (non-fatal): %s", exc)

    try:
        repo.update(
            prd_task.id,
            status="done",
            owner=TaskOwner.PRODUCT_OWNER,
            notes="PRD completed",
        )
    except Exception:
        logger.exception("Failed to update PRD task %s to done", prd_task.id)

    if purpose.mode == "auto" and artifact:
        released = False
        release_error = False
        try:
            with Session(engine) as session:
                art = session.get(Artifact, artifact.id)
                if art:
                    art.released = True
                    session.add(art)
                    session.commit()
                    released = True
                    artifact.released = True
        except Exception:
            release_error = True
            logger.exception(
                "Auto-release of PRD artefact %s failed for purpose %s",
                artifact.id,
                purpose.id,
            )
        if released:
            logger.info(
                "Auto-released PRD artefact %s for purpose %s", artifact.id, purpose.id
            )
        elif not release_error:
            logger.warning(
                "PRD artefact %s for purpose %s not auto-released", artifact.id, purpose.id
            )

    return prd_task, prd_content, artifact


@router.post("/pause")
def pause_pipeline(current_tenant: Tenant = Depends(get_current_tenant)):
    tenant_id = current_tenant.id
    try:
        pool.set(f"pause:{tenant_id}", "1")
    except Exception as e:
        logger.error("Redis set failed: %s", e)
        raise HTTPException(status_code=503, detail="Cache unavailable")
    return {"status": "paused"}


@router.post("/resume")
def resume_pipeline(current_tenant: Tenant = Depends(get_current_tenant)):
    tenant_id = current_tenant.id
    try:
        pool.delete(f"pause:{tenant_id}")
    except Exception as e:
        logger.error("Redis delete failed: %s", e)
        raise HTTPException(status_code=503, detail="Cache unavailable")
    return {"status": "resumed"}


@router.get("/pause")
def get_pause_status(current_tenant: Tenant = Depends(get_current_tenant)):
    tenant_id = current_tenant.id
    try:
        paused = bool(pool.get(f"pause:{tenant_id}"))
    except Exception as e:
        logger.error("Redis get failed: %s", e)
        raise HTTPException(status_code=503, detail="Cache unavailable")
    return {"paused": paused}


@router.get("/graph")
def get_graph(current_tenant: Tenant = Depends(get_current_tenant)):
    """Get all tasks and dependencies as graph data."""
    tenant_id = current_tenant.id
    with Session(engine) as session:
        tasks = session.exec(select(Task).where(Task.tenant_id == tenant_id)).all()
        deps = session.exec(
            select(TaskDependency).where(TaskDependency.from_task.has(tenant_id=tenant_id))
        ).all()
        tasks_data = [t.model_dump() for t in tasks]
        dependencies_data = [{"from_id": d.from_id, "to_id": d.to_id} for d in deps]
    return {"tasks": tasks_data, "dependencies": dependencies_data}


@router.get("/purposes/{purpose_id}/graph", tags=["purposes"])
def get_purpose_graph(purpose_id: str, current_tenant: Tenant = Depends(get_current_tenant)):
    tenant_id = current_tenant.id
    with Session(engine) as session:
        tasks = session.exec(
            select(Task).where(Task.tenant_id == tenant_id, Task.purpose_id == purpose_id)
        ).all()
        deps = session.exec(
            select(TaskDependency).where(
                TaskDependency.from_task.has(tenant_id=tenant_id, purpose_id=purpose_id),
                TaskDependency.to_task.has(tenant_id=tenant_id, purpose_id=purpose_id),
            )
        ).all()
        tasks_data = [t.model_dump() for t in tasks]
        dependencies_data = [{"from_id": d.from_id, "to_id": d.to_id} for d in deps]
    return {"tasks": tasks_data, "dependencies": dependencies_data}


@router.get("/purposes/{purpose_id}/status", tags=["purposes"])
def get_purpose_status(purpose_id: str, current_tenant: Tenant = Depends(get_current_tenant)):
    tenant_id = current_tenant.id
    try:
        paused = bool(pool.get(f"pause:{tenant_id}:{purpose_id}"))
        budget = float(pool.get(f"budget:{tenant_id}:{purpose_id}") or DEFAULT_BUDGET)
    except Exception as e:
        logger.error("Redis get failed: %s", e)
        paused = False
        budget = DEFAULT_BUDGET
    return {"paused": paused, "budget_left": budget, "budget_total": DEFAULT_BUDGET}


@router.get("/backlog")
async def backlog(
    purpose_id: str | None = None, current_tenant: Tenant = Depends(get_current_tenant)
):
    with Session(engine) as s:
        query = select(Task).where(Task.tenant_id == current_tenant.id, Task.status == "todo")
        if purpose_id:
            query = query.where(Task.purpose_id == purpose_id)
        rows = s.exec(query).all()
    return [r.model_dump() for r in rows]


@router.get("/artifacts", tags=["artifacts"])
async def list_artifacts(
    purpose_id: str | None = None, current_tenant: Tenant = Depends(get_current_tenant)
):
    """List all artifacts with related task info."""
    tenant_id = current_tenant.id
    with Session(engine) as session:
        query = (
            select(Artifact)
            .options(selectinload(Artifact.task))
            .where(Artifact.task.has(tenant_id=tenant_id))
        )
        if purpose_id:
            query = query.where(Artifact.task.has(purpose_id=purpose_id))
        artifacts = session.exec(query.order_by(Artifact.created_at)).all()
        result = []
        for art in artifacts:
            result.append(
                {
                    "id": art.id,
                    "task_id": art.task_id,
                    "task_desc": art.task.description if art.task else None,
                    "repo_path": art.repo_path,
                    "media_type": art.media_type,
                    "created_at": art.created_at.isoformat(),
                    "released": art.released,
                    "url": f"/api/artifact/{art.id}",
                }
            )
    return result


@router.get("/purposes", tags=["purposes"])
def list_purposes(current_tenant: Tenant = Depends(get_current_tenant)):
    tenant_id = current_tenant.id
    with Session(engine) as session:
        purposes = session.exec(select(Purpose).where(Purpose.tenant_id == tenant_id)).all()
    return [p.model_dump() for p in purposes]


@router.get("/purposes/{purpose_id}/pipeline", tags=["purposes"])
def get_purpose_pipeline(
    purpose_id: str, current_tenant: Tenant = Depends(get_current_tenant)
):
    with Session(engine) as session:
        purpose = session.exec(
            select(Purpose).where(
                Purpose.id == purpose_id, Purpose.tenant_id == current_tenant.id
            )
        ).first()
        if not purpose:
            raise HTTPException(status_code=404, detail="Purpose not found")
        template = ensure_template_for_purpose(session, purpose)
        return {"template": template_to_dict(template)}


@router.post("/purposes", tags=["purposes"])
def create_purpose(payload: dict, current_tenant: Tenant = Depends(get_current_tenant)):
    """Create a new purpose and seed initial tasks via LLM agents."""
    name = payload.get("purpose") or "Untitled"
    tenant_id = current_tenant.id
    requested_template_id = (
        payload.get("pipeline_template_id")
        or payload.get("template_id")
    )
    template = None
    with Session(engine) as session:
        purpose = session.exec(
            select(Purpose).where(Purpose.name == name, Purpose.tenant_id == tenant_id)
        ).first()
        template_lookup = requested_template_id or (
            purpose.pipeline_template_id if purpose else None
        )
        template = resolve_pipeline_template(session, tenant_id, template_lookup)
        if not purpose:
            purpose = Purpose(
                name=name,
                tenant_id=tenant_id,
                mode=payload.get("mode", "manual"),
                pipeline_template_id=template.id if template else None,
            )
            session.add(purpose)
            session.commit()
            session.refresh(purpose)
            try:
                pool.set(f"budget:{tenant_id}:{purpose.id}", DEFAULT_BUDGET)
            except Exception as e:
                logger.error("Redis set failed: %s", e)
                raise HTTPException(status_code=503, detail="Cache unavailable")
        else:
            updated = False
            if template and purpose.pipeline_template_id != template.id:
                purpose.pipeline_template_id = template.id
                updated = True
            if updated:
                session.add(purpose)
                session.commit()
                session.refresh(purpose)

    instantiate_pipeline_for_purpose(purpose, template)

    with Session(engine) as session:
        existing_tasks = session.exec(
            select(Task).where(Task.tenant_id == tenant_id, Task.purpose_id == purpose.id)
        ).all()
        existing_vision = next(
            (
                t
                for t in existing_tasks
                if (t.description or "").lower().startswith("vision document")
            ),
            None,
        )
        existing_prd = next(
            (
                t
                for t in existing_tasks
                if (t.description or "").lower().startswith("product requirements document")
            ),
            None,
        )

    vision_content = ""
    if existing_vision:
        vision_art = _latest_artifact_for_task(existing_vision.id)
        if vision_art:
            logger.info("Purpose %s already has a Vision artefact", purpose.id)
            vision_content = _read_artifact_text(vision_art)
        else:
            try:
                _, vision_content, _ = _generate_vision_artifact(purpose, existing_vision)
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"Vision generation failed: {exc}")
    else:
        try:
            _, vision_content, _ = _generate_vision_artifact(purpose)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Vision generation failed: {exc}")

    prd_content = ""
    if existing_prd:
        prd_art = _latest_artifact_for_task(existing_prd.id)
        if prd_art:
            logger.info("Purpose %s already has a PRD artefact", purpose.id)
            prd_content = _read_artifact_text(prd_art)
        elif purpose.mode == "auto":
            try:
                _, prd_content, _ = _generate_prd_artifact(purpose, existing_prd)
            except Exception as exc:
                raise HTTPException(
                    status_code=500, detail=f"Requirements gathering failed: {exc}"
                )
    elif purpose.mode == "auto":
        try:
            _, prd_content, _ = _generate_prd_artifact(purpose)
        except Exception as exc:
            raise HTTPException(
                status_code=500, detail=f"Requirements gathering failed: {exc}"
            )

    return {
        "purpose_id": purpose.id,
        "vision": vision_content,
        "requirements": prd_content,
    }


@router.put("/pipeline/phases/{phase_id}", tags=["pipeline"])
def update_pipeline_phase_endpoint(
    phase_id: str, payload: dict, current_tenant: Tenant = Depends(get_current_tenant)
):
    purpose_id = payload.get("purpose_id")
    if not purpose_id:
        raise HTTPException(status_code=400, detail="purpose_id is required")

    scope = payload.get("scope", "purpose")
    allowed_fields = {
        "model_name",
        "tokens_plan_default",
        "prompt_template",
        "agent_role",
        "requires_approval",
    }
    updates = {key: payload[key] for key in allowed_fields if key in payload}
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")

    with Session(engine) as session:
        purpose = session.exec(
            select(Purpose).where(
                Purpose.id == purpose_id,
                Purpose.tenant_id == current_tenant.id,
            )
        ).first()
        if not purpose:
            raise HTTPException(status_code=404, detail="Purpose not found")

        template = update_phase_configuration(
            session,
            purpose=purpose,
            phase_identifier=phase_id,
            updates=updates,
            scope=str(scope),
        )
        session.refresh(purpose)
        instantiate_pipeline_for_purpose(purpose, template)
        template_payload = template_to_dict(template)

    return {"template": template_payload}


@router.get("/artifacts/{artifact_id}/feedback", tags=["artifacts"])
def get_artifact_feedback(
    artifact_id: str,
    session: Session = Depends(get_session),
    current_tenant: Tenant = Depends(get_current_tenant),
):
    """
    Return all feedback entries for an artifact, sorted by version ascending.
    """
    tenant_id = current_tenant.id
    artifact = session.get(Artifact, artifact_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    task = session.get(Task, artifact.task_id)
    if not task or task.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Forbidden for this tenant")

    stmt = (
        select(ChatMessage)
        .outerjoin(
            ChatMessageArtifact,
            ChatMessageArtifact.chat_message_id == ChatMessage.id,
        )
        .where(ChatMessage.tenant_id == tenant_id)
        .where(ChatMessage.intent == ChatIntent.FEEDBACK)
        .where(
            or_(
                ChatMessage.artifact_id == artifact_id,
                ChatMessageArtifact.artifact_id == artifact_id,
            )
        )
        .order_by(asc(ChatMessage.created_at), asc(ChatMessage.id))
    )
    rows = session.exec(stmt).unique().all()

    items: list[dict[str, Any]] = []
    for index, message in enumerate(rows, start=1):
        metadata = getattr(message, "metadata_", None)
        if not isinstance(metadata, dict):
            metadata = {}
        author = metadata.get("author")
        version_meta: int | None = None
        if "version" in metadata:
            try:
                version_meta = int(metadata.get("version"))
            except (TypeError, ValueError):
                version_meta = None
        version = version_meta or index
        if not author:
            if message.role == ChatRole.AGENT:
                author = "Product Owner (AI)"
            elif message.role == ChatRole.USER:
                author = current_tenant.name
            else:
                author = message.role.value.title()
        created_at = getattr(message, "created_at", None)
        items.append(
            {
                "id": message.id,
                "artifact_id": artifact_id,
                "tenant_id": message.tenant_id,
                "author": author,
                "version": version,
                "content": message.content,
                "created_at": created_at.isoformat() if created_at else None,
            }
        )
    return items


def consistency_check(artifact: Artifact, session: Session) -> dict | None:
    impacted_ids: list[str] = []
    impact_level = "low"
    change_type = "informational"
    followup_suggestion: str | None = None
    task_desc = (artifact.task.description if artifact.task else "").lower()
    repo_path = artifact.repo_path.lower()
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
        if arch_artifact:
            followup_suggestion = "Update architecture"
        else:
            followup_suggestion = "Create architecture"
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


@router.post("/artifacts/{artifact_id}/feedback", tags=["artifacts"])
def post_artifact_feedback(
    artifact_id: str,
    payload: dict,
    session: Session = Depends(get_session),
    current_tenant: Tenant = Depends(get_current_tenant),
):
    """
    Store feedback for an artifact.
    Accepts either:
      - {"content": "<free text>"}  OR
      - {"answers": [{"question": "...", "answer": "..."}, ...]}
    """
    tenant_id = current_tenant.id
    author = payload.get("author") or current_tenant.name

    if "approved" in payload:
        logger.warning("Deprecated 'approved' flag received in feedback payload")

    # 1) Normalize payload
    answers = payload.get("answers")
    if answers:
        if not isinstance(answers, list):
            raise HTTPException(status_code=400, detail="Field 'answers' must be a list")
        # store a compact JSON list of QA pairs
        try:
            text = json.dumps(answers, ensure_ascii=False)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid answers format")
    else:
        text = (payload.get("content") or payload.get("feedback") or "").strip()

    if not text:
        raise HTTPException(status_code=400, detail="Feedback content required")

    # 2) Persist
    artifact = session.get(Artifact, artifact_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    task = session.get(Task, artifact.task_id)
    if not task or task.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Forbidden for this tenant")
    purpose = session.get(Purpose, task.purpose_id)

    existing_messages = session.exec(
        select(ChatMessage)
        .outerjoin(
            ChatMessageArtifact,
            ChatMessageArtifact.chat_message_id == ChatMessage.id,
        )
        .where(ChatMessage.tenant_id == tenant_id)
        .where(ChatMessage.intent == ChatIntent.FEEDBACK)
        .where(
            or_(
                ChatMessage.artifact_id == artifact_id,
                ChatMessageArtifact.artifact_id == artifact_id,
            )
        )
    ).unique().all()
    max_version = 0
    fallback_messages = 0
    for existing in existing_messages:
        metadata_existing = getattr(existing, "metadata_", None)
        if isinstance(metadata_existing, dict) and "version" in metadata_existing:
            try:
                value = int(metadata_existing.get("version"))
            except (TypeError, ValueError):
                continue
            if value > max_version:
                max_version = value
        else:
            fallback_messages += 1
    if max_version == 0 and fallback_messages:
        max_version = (fallback_messages + 1) // 2
    version = max_version + 1

    feedback_message = ChatMessage(
        tenant_id=tenant_id,
        purpose_id=purpose.id if purpose else None,
        artifact_id=artifact_id,
        task_id=artifact.task_id,
        role=ChatRole.USER,
        scope=ChatScope.ARTIFACT,
        intent=ChatIntent.FEEDBACK,
        content=text,
        metadata={"author": author, "version": version},
    )
    try:
        session.add(feedback_message)
        session.flush()
        session.add(
            ChatMessageArtifact(
                chat_message_id=feedback_message.id,
                artifact_id=artifact_id,
            )
        )
        session.commit()
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=f"Failed to save feedback: {exc}")

    trivial = {"ok", "fine", "okay", "thanks", "passt", "danke"}
    if text.lower() in trivial:
        ai_reply = "Understood, will apply."
    else:
        from ai_org_backend.agents.product_owner import run_requirements_feedback

        current_prd = ""
        try:
            file_path = resolve_for_read(artifact.repo_path)
            current_prd = file_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to read existing PRD file: %s", e)
            current_prd = ""
        try:
            updated_prd_md = run_requirements_feedback(
                purpose, feedback=text, current_prd=current_prd
            )
            register_artefact(
                artifact.task_id,
                updated_prd_md.encode("utf-8"),
                filename=artifact.repo_path,
                media_type=artifact.media_type,
                allow_overwrite=True,
            )
        except Exception as e:  # pragma: no cover - logging only
            logger.error("PRD update failed: %s", e)
        ai_reply = "Ich arbeite das ein."

    ai_message = ChatMessage(
        tenant_id=tenant_id,
        purpose_id=purpose.id if purpose else None,
        artifact_id=artifact_id,
        task_id=artifact.task_id,
        role=ChatRole.AGENT,
        scope=ChatScope.ARTIFACT,
        intent=ChatIntent.FEEDBACK,
        content=ai_reply,
        metadata={"author": "Product Owner (AI)", "version": version},
    )
    session.add(ai_message)
    session.flush()
    session.add(
        ChatMessageArtifact(
            chat_message_id=ai_message.id,
            artifact_id=artifact_id,
        )
    )
    session.commit()
    # Trigger consistency check for potentially impacted artifacts
    try:
        impacted = consistency_check(artifact, session)
        if impacted:
            agent_msg = ChatMessage(
                tenant_id=tenant_id,
                purpose_id=purpose.id if purpose else None,
                artifact_id=None,
                task_id=artifact.task_id,
                role=ChatRole.AGENT,
                content=json.dumps(impacted, ensure_ascii=False),
            )
            session.add(agent_msg)
            session.commit()
    except Exception as e:
        logger.error("Consistency check failed: %s", e)

    return {"status": "saved", "version": version}


@router.post("/artifacts/{artifact_id}/approve", tags=["artifacts"])
def approve_artifact(
    artifact_id: str,
    session: Session = Depends(get_session),
    current_tenant: Tenant = Depends(get_current_tenant),
):
    tenant_id = current_tenant.id
    artifact = session.get(Artifact, artifact_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    task = session.get(Task, artifact.task_id)
    if not task or task.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Forbidden for this tenant")
    purpose_id = task.purpose_id
    if artifact.released:
        raise HTTPException(status_code=409, detail="Artifact already released")
    task_desc = (task.description or "").lower()
    repo_path = (artifact.repo_path or "").lower()
    is_vision_artifact = "vision" in task_desc or "vision" in repo_path
    response_payload: dict[str, Any] = {"status": "approved"}
    # Mark artifact as released to signal the Orchestrator to continue planning
    artifact.released = True
    session.add(artifact)
    session.commit()
    if is_vision_artifact:
        purpose = session.get(Purpose, purpose_id)
        if purpose:
            existing_prd = session.exec(
                select(Task)
                .where(Task.purpose_id == purpose_id)
                .where(Task.description.ilike("%Product Requirements Document%"))
            ).first()
            if not existing_prd:
                try:
                    _, _, prd_artifact = _generate_prd_artifact(purpose)
                    if prd_artifact:
                        response_payload["artifact_redirect_id"] = prd_artifact.id
                        response_payload["artifact_redirect_url"] = f"/api/artifact/{prd_artifact.id}"
                except Exception as exc:
                    logger.error("PRD generation after vision approval failed: %s", exc)
    try:
        pool.delete(f"pause:{tenant_id}:{purpose_id}")
    except Exception:
        logger.error("Redis delete failed: could not resume purpose %s", purpose_id)
    return response_payload


@router.get("/artifact/{artifact_id}", tags=["artifacts"])
def download_artifact(artifact_id: str, current_tenant: Tenant = Depends(get_current_tenant)):
    """Download the content of an artifact file by ID."""
    tenant_id = current_tenant.id
    with Session(engine) as session:
        art = session.get(Artifact, artifact_id)
        if not art or (art.task and art.task.tenant_id != tenant_id):
            raise HTTPException(status_code=404, detail="Artifact not found")
        file_path = resolve_for_read(art.repo_path)
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Artifact file not found")
    return FileResponse(file_path, media_type=art.media_type, filename=Path(art.repo_path).name)


@router.get("/project.zip")
def download_project_archive(current_tenant: Tenant = Depends(get_current_tenant)):
    """Download a ZIP archive containing all artifacts for the tenant."""
    tenant_id = current_tenant.id
    base_dir = WORKSPACE / tenant_id
    if not base_dir.exists():
        raise HTTPException(status_code=404, detail="No project output available")
    archive_path = base_dir.parent / f"{tenant_id}_output.zip"
    if archive_path.exists():
        archive_path.unlink()
    from shutil import make_archive

    make_archive(str(archive_path.with_suffix("")), "zip", root_dir=base_dir)
    return FileResponse(
        archive_path, media_type="application/zip", filename=f"{tenant_id}_project.zip"
    )


@router.get("/context")
def get_context(task_id: str, current_tenant: Tenant = Depends(get_current_tenant)):
    """Get semantically relevant snippets for a given task."""
    with Session(engine) as session:
        task = session.get(Task, task_id)
        if not task or task.tenant_id != current_tenant.id:
            raise HTTPException(status_code=404, detail="Task not found")
        tenant_id = task.tenant_id
        query_text = task.description
    results = vector_store.query_vectors(tenant_id, query_text, top_k=5)
    snippets: list[dict] = []
    for res in results:
        payload = res.payload or {}
        source = payload.get("file", "")
        snippet_text = ""
        if source:
            file_path = WORKSPACE / source
            if file_path.exists():
                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    content = ""
                snippet_text = content[:500] + ("..." if len(content) > 500 else "")
        snippets.append(
            {"source": source, "snippet": snippet_text, "score": getattr(res, "score", None)}
        )
    return {"task_id": task_id, "snippets": snippets}
