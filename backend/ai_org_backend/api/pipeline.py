import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import func
from sqlmodel import Session, select

from ai_org_backend.api.dependencies import get_current_tenant, get_session
from ai_org_backend.db import engine
from ai_org_backend.models import Artifact, ArtifactFeedback, Purpose, Task, TaskDependency, Tenant
from ai_org_backend.models.chat import ChatMessage, ChatRole
from ai_org_backend.redis_client import DEFAULT_BUDGET, pool
from ai_org_backend.repo import Repo
from ai_org_backend.scripts.seed_graph import ingest
from ai_org_backend.services import budget as budget_svc
from ai_org_backend.services.storage import WORKSPACE, resolve_for_read, save_artefact, vector_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["pipeline"])


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


@router.post("/purposes", tags=["purposes"])
def create_purpose(payload: dict, current_tenant: Tenant = Depends(get_current_tenant)):
    """Create a new purpose and seed initial tasks via LLM agents."""
    name = payload.get("purpose") or "Untitled"
    tenant_id = current_tenant.id
    with Session(engine) as session:
        purpose = session.exec(
            select(Purpose).where(Purpose.name == name, Purpose.tenant_id == tenant_id)
        ).first()
        if not purpose:
            purpose = Purpose(name=name, tenant_id=tenant_id)
            session.add(purpose)
            session.commit()
            session.refresh(purpose)
            try:
                pool.set(f"budget:{tenant_id}:{purpose.id}", DEFAULT_BUDGET)
            except Exception as e:
                logger.error("Redis set failed: %s", e)
                raise HTTPException(status_code=503, detail="Cache unavailable")
    with Session(engine) as session:
        existing_tasks = session.exec(
            select(Task).where(Task.tenant_id == tenant_id, Task.purpose_id == purpose.id)
        ).all()
        existing_prd = next(
            (
                t
                for t in existing_tasks
                if (t.description or "").lower().startswith("product requirements document")
            ),
            None,
        )

    prd_task_obj = existing_prd
    prd_content = ""
    if existing_prd:
        logger.info("Purpose %s already has a PRD, skipping creation", purpose.id)
        with Session(engine) as session:
            art = session.exec(
                select(Artifact)
                .where(Artifact.task_id == existing_prd.id)
                .order_by(Artifact.created_at.desc())
            ).first()
        if art:
            try:
                file_path = resolve_for_read(art.repo_path)
                prd_content = file_path.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning(
                    "Failed to load existing PRD artefact for task %s: %s",
                    existing_prd.id,
                    e,
                )
    else:
        # 1) Generate requirements via Product Owner agent
        try:
            from ai_org_backend.agents.product_owner import run_requirements

            prd_content = run_requirements(purpose)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Requirements gathering failed: {e}")

        # Persist PRD task and artefact
        with Session(engine) as session:
            prd_task_obj = Task(
                tenant_id=tenant_id,
                purpose_id=purpose.id,
                description="Product Requirements Document",
                business_value=0.0,
                tokens_plan=0,
                purpose_relevance=1.0,
            )
            session.add(prd_task_obj)
            session.commit()
            session.refresh(prd_task_obj)

        repo_rel = "requirements/product_requirements.md"
        try:
            save_artefact(
                prd_task_obj.id,
                prd_content.encode("utf-8"),
                filename=repo_rel,
                media_type="text/markdown",
            )
        except Exception as e:
            logger.exception("failed to persist artefact to workspace (%s): %s", repo_rel, e)
        try:
            token_guess = max(1, len(prd_content) // 4)
            budget_svc.debit(
                purpose_id=purpose.id,
                amount=token_guess,
                reason="artifact:requirements",
            )
        except Exception as e:
            logger.warning("budget debit failed (non-fatal): %s", e)
        Repo(tenant_id).update(
            prd_task_obj.id,
            status="done",
            owner="ProductOwner",
            notes="PRD completed",
        )

    return {"purpose_id": purpose.id, "requirements": prd_content}


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
        .order_by(ArtifactFeedback.version.asc())
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
            .order_by(Artifact.created_at.desc())
        ).first()
        if arch_artifact:
            impacted_ids.append(arch_artifact.id)
        test_artifact = session.exec(
            select(Artifact)
            .where(Artifact.task.has(purpose_id=artifact.task.purpose_id))
            .where(Artifact.repo_path.ilike("%test%"))
            .order_by(Artifact.created_at.desc())
        ).first()
        if test_artifact:
            impacted_ids.append(test_artifact.id)
        ui_artifact = session.exec(
            select(Artifact)
            .where(Artifact.task.has(purpose_id=artifact.task.purpose_id))
            .where(Artifact.repo_path.ilike("%ui%"))
            .order_by(Artifact.created_at.desc())
        ).first()
        if ui_artifact:
            impacted_ids.append(ui_artifact.id)
        if arch_artifact:
            followup_suggestion = "Architektur aktualisieren"
        else:
            followup_suggestion = "Architektur erstellen"
    elif "blueprint" in task_desc or "architecture_blueprint" in repo_path:
        impact_level = "medium"
        change_type = "followup_needed"
        test_artifact = session.exec(
            select(Artifact)
            .where(Artifact.task.has(purpose_id=artifact.task.purpose_id))
            .where(Artifact.repo_path.ilike("%test%"))
            .order_by(Artifact.created_at.desc())
        ).first()
        if test_artifact:
            impacted_ids.append(test_artifact.id)
        followup_suggestion = "Testfälle überprüfen"
    elif "ui" in task_desc or "ui" in repo_path:
        impact_level = "medium"
        change_type = "informational"
        test_artifact = session.exec(
            select(Artifact)
            .where(Artifact.task.has(purpose_id=artifact.task.purpose_id))
            .where(Artifact.repo_path.ilike("%test%"))
            .order_by(Artifact.created_at.desc())
        ).first()
        if test_artifact:
            impacted_ids.append(test_artifact.id)
        followup_suggestion = "UI-Tests aktualisieren"
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
        ai_reply = "Verstanden, wird übernommen."
    else:
        from ai_org_backend.agents.product_owner import run_requirements_feedback

        current_prd = ""
        try:
            file_path = resolve_for_read(artifact.repo_path)
            current_prd = file_path.read_text(encoding="utf-8")
        except Exception:
            pass
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

    try:
        from ai_org_backend.agents.architect import run_architect
        from ai_org_backend.agents.planner import run_planner

        purpose_ref = Purpose(id=purpose_id)
        blueprint_md = run_architect(purpose_ref)
        blueprint_task = Task(
            tenant_id=tenant_id,
            purpose_id=purpose_id,
            description="Architecture Blueprint",
            status="done",
        )
        session.add(blueprint_task)
        session.commit()
        session.refresh(blueprint_task)

        save_artefact(
            blueprint_task.id,
            blueprint_md.encode("utf-8"),
            filename="blueprints/architecture_blueprint.md",
            media_type="text/markdown",
            allow_overwrite=True,
        )
        Repo(tenant_id).update(
            blueprint_task.id, status="done", owner="Architect", notes="Blueprint completed"
        )
        # Generate implementation tasks only if none exist yet (skip if an implementation plan already exists)
        existing_task = session.exec(
            select(Task)
            .where(Task.tenant_id == tenant_id, Task.purpose_id == purpose_id, Task.status != "done")
            .where(Task.description != "Product Requirements Document")
            .where(Task.description != "Architecture Blueprint")
            .where(Task.description != "Architecture & Domain Review")
        ).first()
        if not existing_task:
            tasks_plan = run_planner(blueprint_md)
            for t in tasks_plan:
                task_obj = Task(
                    tenant_id=tenant_id,
                    purpose_id=purpose_id,
                    description=t.get("description", ""),
                    business_value=float(t.get("business_value", 1.0)),
                    tokens_plan=int(t.get("tokens_plan", 0)),
                    purpose_relevance=float(t.get("purpose_relevance", 0.0)),
                    status="todo",
                )
                session.add(task_obj)
            session.commit()
        # Mark as released only after successful blueprint (+ any tasks)
        artifact.released = True
        session.add(artifact)
        session.commit()
        logger.info("Artifact %s released for tenant %s", artifact_id, tenant_id)
        try:
            ingest(tenant_id)
        except Exception as e:  # pragma: no cover - logging only
            logger.warning("Neo4j ingest failed: %s", e)
    except Exception as e:  # pragma: no cover - logging only
        logger.error("Blueprint generation failed: %s", e)
    finally:
        try:
            pool.delete(f"pause:{tenant_id}:{purpose_id}")
        except Exception as e:  # pragma: no cover - logging only
            logger.error("Redis delete failed: %s", e)
        if artifact.released:
            try:
                impacted = consistency_check(artifact, session)
                if impacted:
                    agent_msg = ChatMessage(
                        tenant_id=tenant_id,
                        purpose_id=purpose_id,
                        artifact_id=None,
                        task_id=artifact.task_id,
                        role=ChatRole.AGENT,
                        content=json.dumps(impacted, ensure_ascii=False),
                    )
                    session.add(agent_msg)
                    session.commit()
            except Exception as e:
                logger.error("Consistency check failed: %s", e)

    return {"status": "approved"}


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
