import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, select

sys.path.append(str(Path(__file__).resolve().parents[1]))

from ai_org_backend.models import Purpose, Task, Tenant


def create_client(monkeypatch):
    monkeypatch.setitem(os.environ, "DISABLE_METRICS", "1")
    monkeypatch.setitem(os.environ, "REDIS_URL", "redis://localhost:6379/0")
    import tempfile
    import importlib

    fd, path = tempfile.mkstemp()
    os.close(fd)
    db_path = Path(path)
    monkeypatch.setitem(os.environ, "DATABASE_URL", f"sqlite:///{db_path}")

    import ai_org_backend.api.dependencies as dependencies
    import ai_org_backend.api.purposes as purposes_module
    import ai_org_backend.db as db

    importlib.reload(db)
    importlib.reload(dependencies)
    importlib.reload(purposes_module)

    from ai_org_backend.api.dependencies import get_current_tenant
    from ai_org_backend.api.purposes import router
    from ai_org_backend.db import engine

    SQLModel.metadata.create_all(engine)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    return client, app, engine, get_current_tenant


def test_start_purpose_only_resumes_without_creating_prd(monkeypatch):
    client, app, engine, get_current_tenant = create_client(monkeypatch)

    tenant = Tenant(id="tenant123", name="Tenant", hashed_password="x")
    purpose = Purpose(id="purpose1", tenant_id=tenant.id, name="Demo", mode="manual")
    with Session(engine) as session:
        session.add(tenant)
        session.add(purpose)
        session.commit()
        tenant_detached = Tenant(
            id=tenant.id, name=tenant.name, hashed_password=tenant.hashed_password
        )

    app.dependency_overrides[get_current_tenant] = lambda: tenant_detached

    response = client.post(f"/api/purposes/{purpose.id}/start")
    assert response.status_code == 200
    assert response.json()["status"] == "resumed"

    with Session(engine) as session:
        prd_task = session.exec(
            select(Task)
            .where(Task.purpose_id == purpose.id)
            .where(Task.description.ilike("%Product Requirements Document%"))
        ).first()
        assert prd_task is None
