import json
import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select

sys.path.append(str(Path(__file__).resolve().parents[1]))

from ai_org_backend.models import Artifact, Task, Tenant


def create_client(monkeypatch):
    monkeypatch.setitem(os.environ, "DISABLE_METRICS", "1")
    monkeypatch.setitem(os.environ, "REDIS_URL", "redis://localhost:6379/0")
    db_path = Path("test.db")
    if db_path.exists():
        db_path.unlink()
    monkeypatch.setitem(os.environ, "DATABASE_URL", f"sqlite:///{db_path}")
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
