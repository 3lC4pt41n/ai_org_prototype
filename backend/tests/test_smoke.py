import importlib
import os
import sys
import types
from fastapi.testclient import TestClient

openai_stub = types.ModuleType("openai")
class DummyChat:
    @staticmethod
    def create(*args, **kwargs):
        class _Msg:
            content = "ok"
        class _Choice:
            message = _Msg()
        return types.SimpleNamespace(choices=[_Choice()])

openai_stub.ChatCompletion = DummyChat
openai_stub.OpenAIError = Exception
sys.modules.setdefault("openai", openai_stub)

backoff_stub = types.ModuleType("backoff")
def _decorator(*args, **kwargs):
    def wrap(func):
        return func
    return wrap

backoff_stub.on_exception = _decorator
backoff_stub.expo = lambda *a, **kw: 0
sys.modules.setdefault("backoff", backoff_stub)
os.environ["DISABLE_METRICS"] = "1"
os.environ["DATABASE_URL"] = "sqlite:///test.db"
if os.path.exists("test.db"):
    os.remove("test.db")

main = importlib.import_module("ai_org_backend.main")
from sqlmodel import SQLModel  # noqa: E402
from ai_org_backend import models  # noqa: E402
from ai_org_backend.db import SessionLocal  # noqa: E402
from ai_org_backend.models import Artifact, Task  # noqa: E402
from ai_org_backend.services.billing import credit, balance  # noqa: E402

SQLModel.metadata.create_all(main.engine)

client = TestClient(main.app)
r = client.post("/api/register", json={"email": "t@e.st", "password": "pw"})
TENANT = r.json()["id"]
login = client.post("/api/login", data={"username": "t@e.st", "password": "pw"})
TOKEN = login.json()["access_token"]


def test_budget_gate_and_artifact(tmp_path):
    credit(TENANT, 10.0)
    assert balance(TENANT) >= 10.0

    # Purpose und Task direkt anlegen
    with SessionLocal() as db:
        db.add(models.Purpose(id="purp", tenant_id=TENANT, name="pytest-mvp"))
        task = Task(tenant_id=TENANT, description="demo", status="done")
        db.add(task)
        db.commit()

    with SessionLocal() as db:
        task = db.query(Task).first()
        db.add(
            Artifact(
                task_id=task.id,
                repo_path="dummy.txt",
                media_type="text/plain",
                size=4,
                sha256="deadbeef" * 8,
            )
        )
        db.commit()

    arts = client.get("/api/artifacts", headers={"Authorization": f"Bearer {TOKEN}"}).json()
    assert len(arts) == 1
    assert balance(TENANT) >= 10.0
