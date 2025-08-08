import importlib
import os
from fastapi.testclient import TestClient

def get_client(monkeypatch):
    monkeypatch.setitem(os.environ, "DISABLE_METRICS", "1")
    main = importlib.import_module("ai_org_backend.main")
    return TestClient(main.app)


def test_register_login_and_protected_route(monkeypatch):
    client = get_client(monkeypatch)
    # register
    r = client.post("/api/register", json={"email": "a@b.com", "password": "secret"})
    assert r.status_code == 200
    # login
    r = client.post("/api/login", data={"username": "a@b.com", "password": "secret"})
    assert r.status_code == 200
    token = r.json()["access_token"]
    # unauthorized
    resp = client.get("/backlog")
    assert resp.status_code == 401
    # authorized
    resp = client.get("/backlog", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
