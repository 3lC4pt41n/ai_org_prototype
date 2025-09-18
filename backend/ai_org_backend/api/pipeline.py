import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import asc, desc
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import func
from sqlmodel import Session, select

from ai_org_backend.api.dependencies import get_current_tenant, get_session
from ai_org_backend.db import engine
from ai_org_backend.models import Artifact, ArtifactFeedback, Purpose, Task, TaskDependency, Tenant
from ai_org_backend.models.chat import ChatMessage, ChatRole
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
from ai_org_backend.services.storage import WORKSPACE, resolve_for_read, save_artefact, vector_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["pipeline"])


@router.get("/pipeline/templates", tags=["pipeline"])
def list_pipeline_templates_endpoint(
    current_tenant: Tenant = Depends(get_current_tenant),
):
    with Session(engine) as session:
        templates = list_templates_for_tenant(session, current_tenant.id)
        return [template_to_dict(template) for template in templates]


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
            owner="VisionAgent",
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
                owner="VisionAgent",
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
        artifact = save_artefact(
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
                owner="VisionAgent",
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
            owner="VisionAgent",
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
            owner="ProductOwner",
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
                owner="ProductOwner",
                notes=f"PRD agent error: {exc}",
            )
        except Exception:
            logger.exception(
                "Failed to record PRD task failure for task %s", prd_task.id
            )
        raise

    artifact: Artifact | None = None
    repo_rel = "requirements/product_requirements.md"
    try:
        artifact = save_artefact(
            prd_task.id,
            prd_content.encode("utf-8"),
            filename=repo_rel,
            media_type="text/markdown",
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
                owner="ProductOwner",
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
            owner="ProductOwner",
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

    rows = session.exec(
        select(ArtifactFeedback)
        .where(ArtifactFeedback.artifact_id == artifact_id)
        .order_by(asc(ArtifactFeedback.version))
    ).all()

    # Return plain dicts – avoids Pydantic/ORM serialization surprises
    return [
        {
            "id": f.id,
            "artifact_id": f.artifact_id,
            "tenant_id": f.tenant_id,
            "author": f.author,
            "version": f.version,
            "content": f.content,
            "created_at": getattr(f, "created_at", None),
        }
        for f in rows
    ]


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

    # robust scalar max() to avoid row/tuple surprises
    last_version = session.exec(
        select(func.max(ArtifactFeedback.version)).where(
            ArtifactFeedback.artifact_id == artifact_id
        )
    ).first()
    version = (last_version or 0) + 1

    fb = ArtifactFeedback(
        artifact_id=artifact_id,
        tenant_id=tenant_id,
        author=author,
        version=version,
        content=text,
    )
    try:
        session.add(fb)
        session.commit()
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=f"Failed to save feedback: {e}")

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
            save_artefact(
                artifact.task_id,
                updated_prd_md.encode("utf-8"),
                filename=artifact.repo_path,
                media_type=artifact.media_type,
                allow_overwrite=True,
            )
        except Exception as e:  # pragma: no cover - logging only
            logger.error("PRD update failed: %s", e)
        ai_reply = "Ich arbeite das ein."

    ai_fb = ArtifactFeedback(
        artifact_id=artifact_id,
        tenant_id=tenant_id,
        author="Product Owner (AI)",
        content=ai_reply,
        version=version + 1,
    )
    session.add(ai_fb)
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
