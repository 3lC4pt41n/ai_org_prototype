import importlib
import sys
import types

from sqlmodel import SQLModel, Session

from ai_org_backend.models import Task


def test_register_artefact_triggers_vector_store(monkeypatch, tmp_path):
    """Ensure artefact registration stores an embedding."""

    # Stub OpenAI before importing storage module
    openai_stub = types.ModuleType("openai")
    openai_stub.Embedding = types.SimpleNamespace(create=lambda *a, **kw: {"data": [{"embedding": [0.0]}]})
    openai_stub.OpenAIError = Exception
    monkeypatch.setitem(sys.modules, "openai", openai_stub)

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test.db")

    import ai_org_backend.services.storage as storage

    storage = importlib.reload(storage)

    # Use temporary workspace to avoid polluting repo
    monkeypatch.setattr(storage, "WORKSPACE", tmp_path / "ws")
    storage.WORKSPACE.mkdir()

    SQLModel.metadata.create_all(storage.engine)
    with Session(storage.engine) as session:
        session.add(Task(id="t1", tenant_id="demo", description="x", status="done"))
        session.commit()

    monkeypatch.setattr(storage, "_link_neo4j", lambda *a, **k: None)
    monkeypatch.setattr(storage, "_git_commit", lambda *a, **k: None)

    called = {}

    def fake_store(tenant, artifact_id, text, metadata):
        called.update(tenant=tenant, artifact_id=artifact_id, text=text, metadata=metadata)

    monkeypatch.setattr(storage.vector_store, "store_vector", fake_store)

    file_path = tmp_path / "demo.txt"
    file_path.write_text("hello world")

    artefact = storage.register_artefact("t1", file_path)

    assert called["tenant"] == "demo"
    assert called["artifact_id"] == artefact.id
    assert called["text"] == "hello world"
    assert called["metadata"]["task"] == "t1"
