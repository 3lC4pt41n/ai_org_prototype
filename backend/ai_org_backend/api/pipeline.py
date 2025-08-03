import os
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from ai_org_backend.services.storage import vector_store
from sqlmodel import Session, select
from sqlalchemy.orm import selectinload
from ai_org_backend.db import engine
from ai_org_backend.models import Purpose, Task, TaskDependency, Artifact
import sys
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))
from scripts.seed_graph import ingest  # noqa: E402

TENANT = os.getenv("TENANT", "demo")
router = APIRouter(prefix="/api", tags=["pipeline"])


@router.get("/graph")
def get_graph():
    """Get all tasks and dependencies as graph data."""
    with Session(engine) as session:
        tasks = session.exec(select(Task).where(Task.tenant_id == TENANT)).all()
        deps = session.exec(
            select(TaskDependency).where(
                TaskDependency.from_task.has(tenant_id=TENANT)
            )
        ).all()
        tasks_data = [t.model_dump() for t in tasks]
        dependencies_data = [{"from_id": d.from_id, "to_id": d.to_id} for d in deps]
    return {"tasks": tasks_data, "dependencies": dependencies_data}


@router.get("/artifacts")
def list_artifacts():
    """List all artifacts with related task info."""
    with Session(engine) as session:
        artifacts = session.exec(
            select(Artifact)
            .options(selectinload(Artifact.task))
            .where(Artifact.task.has(tenant_id=TENANT))
            .order_by(Artifact.created_at)
        ).all()
        result = []
        for art in artifacts:
            result.append({
                "id": art.id,
                "task_id": art.task_id,
                "task_desc": art.task.description if art.task else None,
                "repo_path": art.repo_path,
                "media_type": art.media_type,
                "created_at": art.created_at.isoformat(),
                "url": f"/artifact/{art.id}"
            })
    return result


@router.post("/purpose")
def create_purpose(payload: dict):
    """Create a new purpose and seed initial tasks via LLM agents."""
    name = payload.get("purpose") or "Untitled"
    # Ensure Purpose exists (create if not)
    with Session(engine) as session:
        purpose = session.exec(
            select(Purpose).where(Purpose.name == name, Purpose.tenant_id == TENANT)
        ).first()
        if not purpose:
            purpose = Purpose(name=name, tenant_id=TENANT)
            session.add(purpose)
            session.commit()
            session.refresh(purpose)
    # Prevent duplicate seeding if tasks already exist for this purpose
    with Session(engine) as session:
        existing_tasks = session.exec(
            select(Task).where(Task.tenant_id == TENANT, Task.purpose_id == purpose.id)
        ).all()
        existing_desc_map = {t.description: t.id for t in existing_tasks}
    if existing_tasks:
        raise HTTPException(status_code=400, detail="Purpose already has tasks")
    # Generate blueprint and task plan via Architect and Planner agents
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
    if not any(str(t.get("description", "")).lower().startswith("initialize repository") for t in tasks_plan):
        tasks_plan.insert(0, {
            "id": "repo_init",
            "description": "Initialize repository scaffolding",
            "business_value": 1.0,
            "tokens_plan": 0,
            "purpose_relevance": 0.0
        })
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
                tenant_id=TENANT,
                purpose_id=purpose.id,
                description=t["description"],
                business_value=t.get("business_value", 1.0),
                tokens_plan=t.get("tokens_plan", 0),
                purpose_relevance=t.get("purpose_relevance", 0.0)
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
        # Ensure all new tasks depend on repo_init (if present)
        repo_id = id_map.get("repo_init")
        if repo_id:
            for slug, tid in id_map.items():
                if slug != "repo_init":
                    session.add(TaskDependency(from_id=repo_id, to_id=tid))
        session.commit()
    # Update Neo4j graph
    try:
        ingest(TENANT)
    except Exception as e:
        print(f"[WARN] Neo4j ingest failed: {e}")
    return {"blueprint": blueprint}


@router.get("/artifact/{artifact_id}")
def download_artifact(artifact_id: str):
    """Download the content of an artifact file by ID."""
    with Session(engine) as session:
        art = session.get(Artifact, artifact_id)
        if not art:
            raise HTTPException(status_code=404, detail="Artifact not found")
        file_path = Path("workspace") / art.repo_path
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Artifact file not found")
    return FileResponse(file_path, media_type=art.media_type, filename=Path(art.repo_path).name)


@router.get("/project.zip")
def download_project_archive():
    """Download a ZIP archive containing all artifacts for the tenant."""
    base_dir = Path("workspace") / TENANT
    if not base_dir.exists():
        raise HTTPException(status_code=404, detail="No project output available")
    archive_path = base_dir.parent / f"{TENANT}_output.zip"
    if archive_path.exists():
        archive_path.unlink()
    from shutil import make_archive
    make_archive(str(archive_path.with_suffix("")), "zip", root_dir=base_dir)
    return FileResponse(archive_path, media_type="application/zip", filename=f"{TENANT}_project.zip")


@router.get("/context")
def get_context(task_id: str):
    """Get semantically relevant snippets for a given task."""
    # Fetch task and ensure it exists
    with Session(engine) as session:
        task = session.get(Task, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        tenant_id = task.tenant_id
        query_text = task.description
    # Query vector store for relevant snippets
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
        snippets.append({
            "source": source,
            "snippet": snippet_text,
            "score": getattr(res, "score", None)
        })
    return {"task_id": task_id, "snippets": snippets}
