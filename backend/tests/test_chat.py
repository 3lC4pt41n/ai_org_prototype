import os
import sys
import tempfile
import types
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select

sys.path.append(str(Path(__file__).resolve().parents[1]))


def create_client(monkeypatch):
    monkeypatch.setitem(os.environ, "DISABLE_METRICS", "1")
    monkeypatch.setitem(os.environ, "REDIS_URL", "redis://localhost:6379/0")
    fd, path = tempfile.mkstemp()
    os.close(fd)
    monkeypatch.setitem(os.environ, "DATABASE_URL", f"sqlite:///{path}")
    import importlib

    import ai_org_backend.api.dependencies as dependencies
    import ai_org_backend.db as db

    importlib.reload(db)
    importlib.reload(dependencies)

    openai_stub = types.ModuleType("openai")
    openai_stub.ChatCompletion = SimpleNamespace(
        create=lambda **kwargs: {"choices": [{"message": {"content": "Stubbed answer"}}]}
    )
    openai_stub.OpenAIError = Exception
    monkeypatch.setitem(sys.modules, "openai", openai_stub)

    po_stub = types.ModuleType("ai_org_backend.agents.product_owner")
    po_stub.run_requirements_feedback = lambda *args, **kwargs: ""
    monkeypatch.setitem(sys.modules, "ai_org_backend.agents.product_owner", po_stub)

    import ai_org_backend.services.storage as storage

    monkeypatch.setattr(storage, "WORKSPACE", Path(tempfile.mkdtemp()) / "ws")
    monkeypatch.setattr(storage, "_git_commit", lambda *args, **kwargs: None)
    monkeypatch.setattr(storage, "_link_neo4j", lambda *args, **kwargs: None)
    monkeypatch.setattr(storage.vector_store, "store_vector", lambda *args, **kwargs: True)

    import ai_org_backend.api.chat as chat_module

    SQLModel.metadata.create_all(db.engine)
    app = FastAPI()
    app.include_router(chat_module.router)
    client = TestClient(app)
    return client, db.engine


def override_get_current_tenant(tenant):
    return lambda: tenant


def setup_base_data(engine):
    from ai_org_backend.models import Artifact, Purpose, Task, Tenant

    tenant = Tenant(id="tenant1", name="TestTenant", hashed_password="x")
    purpose = Purpose(id="purpose1", tenant_id=tenant.id, name="Demo Project")
    prd_task = Task(
        id="taskprd",
        tenant_id=tenant.id,
        purpose_id=purpose.id,
        description="Product Requirements Document",
        status="done",
    )
    artifact = Artifact(
        id="artifact1",
        task_id=prd_task.id,
        repo_path="requirements/product_requirements.md",
        media_type="text/markdown",
        size=0,
        sha256="0" * 64,
    )
    with Session(engine, expire_on_commit=False) as session:
        session.add(tenant)
        session.add(purpose)
        session.add(prd_task)
        session.add(artifact)
        session.commit()
    return tenant, purpose, artifact


def test_chat_history_empty(monkeypatch):
    client, engine = create_client(monkeypatch)
    tenant, purpose, artifact = setup_base_data(engine)
    from ai_org_backend.api.dependencies import get_current_tenant, oauth2_scheme

    client.app.dependency_overrides[get_current_tenant] = override_get_current_tenant(tenant)
    client.app.dependency_overrides[oauth2_scheme] = lambda: "token"
    res = client.get(f"/api/chat/history?purpose_id={purpose.id}")
    assert res.status_code == 200
    assert res.json() == []


def test_chat_simple_reply(monkeypatch):
    client, engine = create_client(monkeypatch)
    tenant, purpose, artifact = setup_base_data(engine)
    from ai_org_backend.api.dependencies import get_current_tenant, oauth2_scheme

    client.app.dependency_overrides[get_current_tenant] = override_get_current_tenant(tenant)
    client.app.dependency_overrides[oauth2_scheme] = lambda: "token"
    payload = {"purpose_id": purpose.id, "message": "Hello AImar!"}
    r = client.post("/api/chat", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["role"] == "assistant"
    assert "Stubbed answer" in data["content"]
    hist_res = client.get(f"/api/chat/history?purpose_id={purpose.id}")
    hist = hist_res.json()
    roles = [m["role"] for m in hist]
    assert roles == ["user", "assistant"]
    assert hist[-1]["content"] == data["content"]


def test_chat_feedback_flow(monkeypatch):
    client, engine = create_client(monkeypatch)
    tenant, purpose, artifact = setup_base_data(engine)
    from ai_org_backend.api.dependencies import get_current_tenant, oauth2_scheme

    client.app.dependency_overrides[get_current_tenant] = override_get_current_tenant(tenant)
    client.app.dependency_overrides[oauth2_scheme] = lambda: "token"
    import ai_org_backend.api.chat as chat_module

    monkeypatch.setattr(chat_module, "pool", SimpleNamespace(get=lambda key: b"1"))
    feedback_msg = "Fehlt Akzeptanzkriterium"
    r = client.post("/api/chat", json={"purpose_id": purpose.id, "message": feedback_msg})
    assert r.status_code == 200
    data = r.json()
    assert data["role"] == "assistant"
    assert "Ich arbeite das ein" in data["content"]
    with Session(engine) as session:
        from ai_org_backend.models import Artifact

        artifacts = session.exec(select(Artifact).where(Artifact.task_id == artifact.task_id)).all()
        assert len(artifacts) >= 2
        latest_art = artifacts[-1]
        assert latest_art.repo_path == artifact.repo_path
