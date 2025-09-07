import json
import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select

sys.path.append(str(Path(__file__).resolve().parents[1]))

from ai_org_backend.models import Artifact, Purpose, Task, Tenant


def create_client(monkeypatch):
    monkeypatch.setitem(os.environ, "DISABLE_METRICS", "1")
    monkeypatch.setitem(os.environ, "REDIS_URL", "redis://localhost:6379/0")
    db_path = Path("test.db")
    if db_path.exists():
        db_path.unlink()
    monkeypatch.setitem(os.environ, "DATABASE_URL", f"sqlite:///{db_path}")
    import types
    from types import SimpleNamespace

    neo4j_stub = types.ModuleType("neo4j")
    neo4j_stub.GraphDatabase = SimpleNamespace(
        driver=lambda *a, **k: SimpleNamespace(
            session=lambda *a, **k: SimpleNamespace(run=lambda *a, **k: None, close=lambda: None)
        )
    )
    monkeypatch.setitem(sys.modules, "neo4j", neo4j_stub)
    from ai_org_backend.api.dependencies import get_current_tenant
    from ai_org_backend.api.pipeline import router
    from ai_org_backend.db import engine  # imported after env vars

    SQLModel.metadata.create_all(engine)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    return client, app, engine, get_current_tenant


def test_artifact_feedback_flow(monkeypatch):
    client, app, engine, get_current_tenant = create_client(monkeypatch)

    tenant = Tenant(id="tenant123", name="TestTenant", hashed_password="x")
    task = Task(id="task1", tenant_id=tenant.id, description="Test Task")
    artifact = Artifact(
        id="artifact1",
        task_id=task.id,
        repo_path="dummy.txt",
        media_type="text/plain",
        size=0,
        sha256="0" * 64,
    )
    artifact_id = artifact.id
    with Session(engine) as session:
        session.add(tenant)
        session.add(task)
        session.add(artifact)
        session.commit()
        tenant_detached = Tenant(
            id=tenant.id, name=tenant.name, hashed_password=tenant.hashed_password
        )

    app.dependency_overrides[get_current_tenant] = lambda: tenant_detached

    r = client.get(f"/api/artifacts/{artifact_id}/feedback")
    assert r.status_code == 200
    assert r.json() == []

    r = client.post(
        f"/api/artifacts/{artifact_id}/feedback",
        json={"content": "Great job on this artifact!"},
    )
    assert r.status_code == 200
    assert r.json()["version"] == 1

    qa_payload = {"answers": [{"question": "Q1?", "answer": "A1."}]}
    r = client.post(f"/api/artifacts/{artifact_id}/feedback", json=qa_payload)
    assert r.status_code == 200
    assert r.json()["version"] == 2

    r = client.get(f"/api/artifacts/{artifact_id}/feedback")
    data = r.json()
    assert len(data) == 2
    assert data[0]["content"] == "Great job on this artifact!"
    assert data[1]["content"] == json.dumps(qa_payload["answers"], ensure_ascii=False)

    with Session(engine) as session:
        tasks = session.exec(select(Task).where(Task.tenant_id == tenant.id)).all()
    assert any(t.description.startswith("Review PRD based on feedback by") for t in tasks)


def test_approval_creates_blueprint(monkeypatch, tmp_path):
    client, app, engine, get_current_tenant = create_client(monkeypatch)

    # stub external services used by save_artefact and approval workflow
    import types
    from types import SimpleNamespace

    from sqlmodel import Session as SQLSession

    import ai_org_backend.api.pipeline as pipeline
    import ai_org_backend.services.storage as storage

    openai_stub = types.ModuleType("openai")
    openai_stub.Embedding = SimpleNamespace(create=lambda *a, **k: {"data": [{"embedding": [0.0]}]})
    openai_stub.OpenAIError = Exception
    monkeypatch.setitem(sys.modules, "openai", openai_stub)

    monkeypatch.setattr(storage, "WORKSPACE", tmp_path / "ws")
    storage.WORKSPACE.mkdir()
    monkeypatch.setattr(storage, "_link_neo4j", lambda *a, **k: None)
    monkeypatch.setattr(storage, "_git_commit", lambda *a, **k: None)
    monkeypatch.setattr(storage.vector_store, "store_vector", lambda *a, **k: True)

    class DummyRepo:
        def __init__(self, tenant_id):
            pass

        def update(self, *a, **k):
            pass

    monkeypatch.setattr(pipeline, "Repo", DummyRepo)
    monkeypatch.setattr(pipeline, "pool", SimpleNamespace(delete=lambda *a, **k: None))
    monkeypatch.setattr(
        pipeline, "Session", lambda *a, **k: SQLSession(*a, **k, expire_on_commit=False)
    )

    architect_stub = types.ModuleType("ai_org_backend.agents.architect")
    architect_stub.run_architect = lambda purpose: "# bp"
    monkeypatch.setitem(sys.modules, "ai_org_backend.agents.architect", architect_stub)

    planner_stub = types.ModuleType("ai_org_backend.agents.planner")
    planner_stub.run_planner = lambda bp: []
    monkeypatch.setitem(sys.modules, "ai_org_backend.agents.planner", planner_stub)

    tenant_id = "tenant123"
    purpose_id = "purpose1"
    tenant = Tenant(id=tenant_id, name="TestTenant", hashed_password="x")
    purpose = Purpose(id=purpose_id, tenant_id=tenant_id, name="Demo")
    task = Task(
        id="task1",
        tenant_id=tenant_id,
        purpose_id=purpose_id,
        description="PRD",
        status="done",
    )
    artifact = Artifact(
        id="artifact1",
        task_id=task.id,
        repo_path="product_requirements.md",
        media_type="text/markdown",
        size=0,
        sha256="0" * 64,
    )

    with Session(engine) as session:
        session.add(tenant)
        session.add(purpose)
        session.add(task)
        session.add(artifact)
        session.commit()
        artifact_id = artifact.id
        tenant_detached = Tenant(
            id=tenant.id, name=tenant.name, hashed_password=tenant.hashed_password
        )

    app.dependency_overrides[get_current_tenant] = lambda: tenant_detached

    r = client.post(
        f"/api/artifacts/{artifact_id}/feedback",
        json={"content": "ok", "approved": True},
    )
    assert r.status_code == 200
    assert r.json()["version"] == 1

    workspace = storage.WORKSPACE
    blueprint_path = workspace / tenant_id / purpose_id / "blueprints" / "architecture_blueprint.md"
    assert blueprint_path.exists()
