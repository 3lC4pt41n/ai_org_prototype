import importlib
import sys
import json

from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, select


def _setup_app(monkeypatch, tmp_path):
    monkeypatch.setenv("DISABLE_METRICS", "1")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    from pathlib import Path
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    for mod in ["ai_org_backend.db", "ai_org_backend.main", "ai_org_backend.api.dependencies"]:
        monkeypatch.delitem(sys.modules, mod, raising=False)
    main = importlib.import_module("ai_org_backend.main")
    from ai_org_backend.db import engine
    SQLModel.metadata.create_all(engine)
    return main.app, engine


def test_artifact_feedback_flow(monkeypatch, tmp_path):
    app, engine = _setup_app(monkeypatch, tmp_path)
    from ai_org_backend.models import Tenant, Task, Artifact
    from ai_org_backend.api.dependencies import get_current_tenant

    tenant = Tenant(id="tenant123", name="TestTenant", hashed_password="x")
    task = Task(id="task1", tenant_id=tenant.id, description="Test Task", status="done")
    artifact = Artifact(
        id="artifact1",
        task_id=task.id,
        repo_path="dummy.txt",
        media_type="text/plain",
        size=0,
        sha256="0" * 64,
    )
    with Session(engine) as session:
        session.add(tenant)
        session.add(task)
        session.add(artifact)
        session.commit()
        session.refresh(tenant)
        session.expunge(tenant)

    app.dependency_overrides[get_current_tenant] = lambda: tenant
    client = TestClient(app)

    # Initially empty
    res = client.get("/api/artifacts/artifact1/feedback")
    assert res.status_code == 200
    assert res.json() == []

    # Post text feedback
    res = client.post(
        "/api/artifacts/artifact1/feedback",
        json={"content": "Great job on this artifact!"},
    )
    assert res.status_code == 200
    assert res.json()["version"] == 1

    # Post Q&A feedback
    qa_payload = {"answers": [{"question": "Q1?", "answer": "A1."}]}
    res2 = client.post("/api/artifacts/artifact1/feedback", json=qa_payload)
    assert res2.status_code == 200
    assert res2.json()["version"] == 2

    # Retrieve list
    res3 = client.get("/api/artifacts/artifact1/feedback")
    assert res3.status_code == 200
    data = res3.json()
    assert len(data) == 2
    assert data[0]["content"] == "Great job on this artifact!"
    assert data[1]["content"] == json.dumps(qa_payload["answers"], ensure_ascii=False)

    # Backlog tasks created for feedback
    with Session(engine) as session:
        tasks = session.exec(select(Task).where(Task.tenant_id == tenant.id)).all()
    review_tasks = [t for t in tasks if t.description.startswith("Review PRD based on feedback by")]
    assert len(review_tasks) == 2
