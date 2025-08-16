import importlib
import os

import ai_org_backend.services.budget as budget
from fastapi.testclient import TestClient


def test_root_get(monkeypatch):
    monkeypatch.setitem(os.environ, "DISABLE_METRICS", "1")
    main = importlib.import_module("ai_org_backend.main")
    monkeypatch.setattr(budget, "get_left", lambda tid: 0)
    monkeypatch.setattr(budget, "get_total", lambda tid: 0)
    client = TestClient(main.app)
    resp = client.get("/")
    assert resp.status_code == 200
