from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import selectinload
from sqlmodel import Session, select

from ai_org_backend.api.dependencies import get_current_tenant
from ai_org_backend.db import engine
from ai_org_backend.models import Artifact, Purpose, Task, TaskDependency, Tenant
from ai_org_backend.redis_client import DEFAULT_BUDGET, pool
from ai_org_backend.repo import Repo
from ai_org_backend.scripts.seed_graph import ingest
from ai_org_backend.services.storage import save_artefact, vector_store

router = APIRouter(prefix="/api", tags=["pipeline"])


@router.post("/pause")
def pause_pipeline(current_tenant: Tenant = Depends(get_current_tenant)):
    tenant_id = current_tenant.id
    pool.set(f"pause:{tenant_id}", "1")
    return {"status": "paused"}


@router.post("/resume")
def resume_pipeline(current_tenant: Tenant = Depends(get_current_tenant)):
    tenant_id = current_tenant.id
    pool.delete(f"pause:{tenant_id}")
    return {"status": "resumed"}


@router.get("/pause")
def get_pause_status(current_tenant: Tenant = Depends(get_current_tenant)):
    tenant_id = current_tenant.id
    paused = bool(pool.get(f"pause:{tenant_id}"))
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


@router.get("/purpose/{purpose_id}/graph")
def get_purpose_graph(purpose_id: str, current_tenant: Tenant = Depends(get_current_tenant)):
    tenant_id = current_tenant.id
    with Session(engine) as session:
        tasks = session.exec(
            select(Task).where(
                Task.tenant_id == tenant_id, Task.purpose_id == purpose_id
            )
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


@router.post("/purpose/{purpose_id}/pause")
def pause_purpose(purpose_id: str, current_tenant: Tenant = Depends(get_current_tenant)):
    tenant_id = current_tenant.id
    pool.set(f"pause:{tenant_id}:{purpose_id}", "1")
    return {"status": "paused"}


@router.post("/purpose/{purpose_id}/resume")
def resume_purpose(purpose_id: str, current_tenant: Tenant = Depends(get_current_tenant)):
    tenant_id = current_tenant.id
    pool.delete(f"pause:{tenant_id}:{purpose_id}")
    return {"status": "resumed"}


@router.get("/purpose/{purpose_id}/status")
def get_purpose_status(purpose_id: str, current_tenant: Tenant = Depends(get_current_tenant)):
    tenant_id = current_tenant.id
    paused = bool(pool.get(f"pause:{tenant_id}:{purpose_id}"))
    budget = float(pool.get(f"budget:{tenant_id}:{purpose_id}") or DEFAULT_BUDGET)
    return {"paused": paused, "budget_left": budget, "budget_total": DEFAULT_BUDGET}


@router.get("/artifacts")
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
                    "url": f"/artifact/{art.id}",
                }
            )
    return result


@router.get("/purpose")
def list_purposes(current_tenant: Tenant = Depends(get_current_tenant)):
    tenant_id = current_tenant.id
    with Session(engine) as session:
        purposes = session.exec(
            select(Purpose).where(Purpose.tenant_id == tenant_id)
        ).all()
    return [p.model_dump() for p in purposes]


@router.post("/purpose")
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
            pool.set(f"budget:{tenant_id}:{purpose.id}", DEFAULT_BUDGET)
    with Session(engine) as session:
        existing_tasks = session.exec(
            select(Task).where(Task.tenant_id == tenant_id, Task.purpose_id == purpose.id)
        ).all()
        existing_desc_map = {t.description: t.id for t in existing_tasks}
    if existing_tasks:
        raise HTTPException(status_code=400, detail="Purpose already has tasks")

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

    save_artefact(
        prd_task_obj.id,
        prd_content.encode("utf-8"),
        filename="requirements/product_requirements.md",
    )
    Repo(tenant_id).update(
        prd_task_obj.id, status="done", owner="ProductOwner", notes="PRD completed"
    )

    # 2) Generate blueprint and task plan via Architect and Planner agents
    try:
        from ai_org_backend.agents.architect import run_architect
        from ai_org_backend.agents.planner import run_planner

        blueprint = run_architect(purpose)
        tasks_plan = run_planner(blueprint)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Seed generation failed: {e}")

    if not tasks_plan or not isinstance(tasks_plan, list):
        raise HTTPException(status_code=500, detail="No tasks generated")

    # Insert repository initialization task if not present
    if not any(
        str(t.get("description", "")).lower().startswith("initialize repository")
        for t in tasks_plan
    ):
        tasks_plan.insert(
            0,
            {
                "id": "repo_init",
                "description": "Initialize repository scaffolding",
                "business_value": 1.0,
                "tokens_plan": 0,
                "purpose_relevance": 0.0,
            },
        )

    # Append Architecture Blueprint task
    tasks_plan.append(
        {
            "id": "blueprint",
            "description": "Architecture Blueprint",
            "business_value": 0.0,
            "tokens_plan": 0,
            "purpose_relevance": 0.0,
        }
    )

    # Filter out duplicates (if any)
    new_tasks = []
    id_map: dict[str, str] = {}
    for t in tasks_plan:
        desc = t["description"]
        if desc in existing_desc_map:
            id_map[t["id"]] = existing_desc_map[desc]
        else:
            new_tasks.append(t)
    tasks_plan = new_tasks

    # Save new tasks in database
    with Session(engine) as session:
        for t in tasks_plan:
            task_obj = Task(
                tenant_id=tenant_id,
                purpose_id=purpose.id,
                description=t["description"],
                business_value=t.get("business_value", 1.0),
                tokens_plan=t.get("tokens_plan", 0),
                purpose_relevance=t.get("purpose_relevance", 0.0),
            )
            session.add(task_obj)
            session.flush()  # obtain task_obj.id
            id_map[t["id"]] = task_obj.id
        session.commit()

        # Create dependency relations
        for t in tasks_plan:
            dep = t.get("depends_on") or t.get("depends_on_id")
            if dep and dep in id_map:
                session.add(TaskDependency(from_id=id_map[dep], to_id=id_map[t["id"]]))

        # Ensure proper task order dependencies
        repo_id = id_map.get("repo_init")
        blueprint_id = id_map.get("blueprint")
        if blueprint_id and repo_id:
            session.add(TaskDependency(from_id=prd_task_obj.id, to_id=blueprint_id))
            session.add(TaskDependency(from_id=blueprint_id, to_id=repo_id))
            for slug, tid in id_map.items():
                if slug not in ("repo_init", "blueprint"):
                    session.add(TaskDependency(from_id=repo_id, to_id=tid))
        elif repo_id:
            for slug, tid in id_map.items():
                if slug != "repo_init":
                    session.add(TaskDependency(from_id=repo_id, to_id=tid))
        session.commit()

    # Update Neo4j graph
    try:
        ingest(tenant_id)
    except Exception as e:
        print(f"[WARN] Neo4j ingest failed: {e}")

    return {"purpose_id": purpose.id, "requirements": prd_content, "blueprint": blueprint}


@router.get("/artifact/{artifact_id}")
def download_artifact(artifact_id: str, current_tenant: Tenant = Depends(get_current_tenant)):
    """Download the content of an artifact file by ID."""
    tenant_id = current_tenant.id
    with Session(engine) as session:
        art = session.get(Artifact, artifact_id)
        if not art or (art.task and art.task.tenant_id != tenant_id):
            raise HTTPException(status_code=404, detail="Artifact not found")
        file_path = Path("workspace") / art.repo_path
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Artifact file not found")
    return FileResponse(file_path, media_type=art.media_type, filename=Path(art.repo_path).name)


@router.get("/project.zip")
def download_project_archive(current_tenant: Tenant = Depends(get_current_tenant)):
    """Download a ZIP archive containing all artifacts for the tenant."""
    tenant_id = current_tenant.id
    base_dir = Path("workspace") / tenant_id
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
            file_path = Path("workspace") / source
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
