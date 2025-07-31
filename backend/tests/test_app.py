from fastapi.testclient import TestClient
import importlib
import os


def test_root_get(monkeypatch):
    monkeypatch.setitem(os.environ, "DISABLE_METRICS", "1")
    main = importlib.import_module("ai_org_backend.main")
    monkeypatch.setattr(main, "budget_left", lambda tenant="demo": 0)
    client = TestClient(main.app)
    resp = client.get("/")
    assert resp.status_code == 200
