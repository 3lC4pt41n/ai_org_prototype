import sys
import types
from types import SimpleNamespace

from sqlmodel import Session, SQLModel


def test_register_artefact_overwrites(monkeypatch, tmp_path):
    openai_stub = types.ModuleType("openai")
    openai_stub.Embedding = types.SimpleNamespace(  # type: ignore[attr-defined]
        create=lambda *a, **kw: {"data": [{"embedding": [0.0]}]}
    )
    openai_stub.OpenAIError = Exception  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "openai", openai_stub)

    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg2://postgres:ai@localhost:5432/ai_org_test"
    )

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
    from ai_org_backend.models import Task

    with Session(storage.engine) as session:
        session.add(Task(id="t1", tenant_id="demo", description="x", status="done"))
        session.commit()

    monkeypatch.setattr(storage, "_link_neo4j", lambda *a, **k: None)  # type: ignore[attr-defined]
    monkeypatch.setattr(storage, "_git_commit", lambda *a, **k: None)  # type: ignore[attr-defined]
    monkeypatch.setattr(storage.vector_store, "store_vector", lambda *a, **k: True)  # type: ignore[attr-defined]

    file1 = tmp_path / "demo.txt"
    file1.write_text("v1")
    art1 = storage.register_artefact("t1", file1)

    file2 = tmp_path / "demo2.txt"
    file2.write_text("v2")
    art2 = storage.register_artefact("t1", file2, filename="demo.txt", allow_overwrite=True)

    assert art2.repo_path == art1.repo_path
    path = storage.WORKSPACE / "demo" / "demo.txt"
    assert path.read_text() == "v2"
    assert art1.id != art2.id
