from fastapi.testclient import TestClient
import ai_org_backend.main as main


def test_root_get(monkeypatch):
    monkeypatch.setattr(main, "budget_left", lambda tenant="demo": 0)
    client = TestClient(main.app)
    resp = client.get("/")
    assert resp.status_code == 200
