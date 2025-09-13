import sys
import types
from types import SimpleNamespace

from sqlmodel import Session, SQLModel


def test_register_artefact_with_purpose(monkeypatch, tmp_path):
    openai_stub = types.ModuleType("openai")
    openai_stub.Embedding = SimpleNamespace(  # type: ignore[attr-defined]
         create=lambda *a, **kw: {"data": [{"embedding": [0.0]}]}
    )
    openai_stub.OpenAIError = Exception  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "openai", openai_stub)

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setattr(
        "ai_org_backend.metrics.prom_counter",
        lambda *a, **k: SimpleNamespace(inc=lambda: None),
        raising=False,
    )
    monkeypatch.delitem(sys.modules, "ai_org_backend.db", raising=False)
    monkeypatch.delitem(sys.modules, "ai_org_backend.services.storage", raising=False)
    import ai_org_backend.services.storage as storage

    monkeypatch.setattr(storage, "WORKSPACE", tmp_path / "ws")
    storage.WORKSPACE.mkdir()

    SQLModel.metadata.create_all(storage.engine)
    SQLModel.metadata.drop_all(storage.engine)
    SQLModel.metadata.create_all(storage.engine)

    from ai_org_backend.models import Purpose, Task

    with Session(storage.engine) as session:
        session.add(Purpose(id="p1", tenant_id="demo", name="demo"))
        session.add(
            Task(
                id="t1",
                tenant_id="demo",
                purpose_id="p1",
                description="demo",
                status="done",
            )
        )
        session.commit()

    monkeypatch.setattr(storage, "_link_neo4j", lambda *a, **k: None)  # type: ignore[attr-defined]
    monkeypatch.setattr(storage, "_git_commit", lambda *a, **k: None)  # type: ignore[attr-defined]
    monkeypatch.setattr(storage.vector_store, "store_vector", lambda *a, **k: True)  # type: ignore[attr-defined]

    file_path = tmp_path / "demo.txt"
    file_path.write_text("hello world" * 10)
    artefact = storage.register_artefact("t1", file_path)

    assert "p1" in artefact.repo_path
    assert (storage.WORKSPACE / artefact.repo_path).exists()
