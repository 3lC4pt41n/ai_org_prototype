import importlib
import os
import tempfile

from ai_org_backend.models import Tenant, UserTheme
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel


def create_client(monkeypatch):
    monkeypatch.setitem(os.environ, "DISABLE_METRICS", "1")
    monkeypatch.setitem(os.environ, "REDIS_URL", "redis://localhost:6379/0")
    fd, path = tempfile.mkstemp()
    os.close(fd)
    monkeypatch.setitem(os.environ, "DATABASE_URL", f"sqlite:///{path}")
    import ai_org_backend.api.dependencies as dependencies
    import ai_org_backend.db as db
    importlib.reload(db)
    importlib.reload(dependencies)
    from ai_org_backend.api.settings import router
    SQLModel.metadata.create_all(db.engine)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    return client, app, db.engine, dependencies.get_current_tenant


def test_theme_setting_roundtrip(monkeypatch):
    client, app, engine, get_current_tenant = create_client(monkeypatch)
    tenant = Tenant(id="tenant1", name="TestTenant", hashed_password="x")
    with Session(engine, expire_on_commit=False) as session:
        session.add(tenant)
        session.commit()
        tenant_detached = Tenant(
            id=tenant.id, name=tenant.name, hashed_password=tenant.hashed_password
        )
    app.dependency_overrides[get_current_tenant] = lambda: tenant_detached

    r = client.get("/api/settings/theme")
    assert r.status_code == 200
    assert r.json() == {"theme": "light"}

    r = client.post("/api/settings/theme", json={"theme": "dark"})
    assert r.status_code == 200
    assert r.json() == {"theme": "dark"}

    with Session(engine) as session:
        t = session.get(Tenant, tenant.id)
        assert t and t.theme == UserTheme.dark

    r = client.get("/api/settings/theme")
    assert r.json() == {"theme": "dark"}
