import sys
import types
from types import SimpleNamespace

from sqlmodel import Session, SQLModel


def test_register_artefact_appends_md(monkeypatch, tmp_path):
    openai_stub = types.ModuleType("openai")
    openai_stub.Embedding = SimpleNamespace(
        create=lambda *a, **kw: {"data": [{"embedding": [0.0]}]}
    )
    openai_stub.OpenAIError = Exception
    monkeypatch.setitem(sys.modules, "openai", openai_stub)

    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg2://postgres:ai@localhost:5432/ai_org_test"
    )
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")

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

    monkeypatch.setattr(storage, "_link_neo4j", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(storage, "_git_commit", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(storage.vector_store, "store_vector", lambda *a, **k: True, raising=False)

    art = storage.register_artefact(
        "t1",
        b"# Title",
        filename="reviews/architecture_domain_review",
        media_type="text/markdown",
        allow_overwrite=True,
    )

    assert art.media_type == "text/markdown"
    assert art.repo_path.endswith("reviews/architecture_domain_review.md")
    assert (storage.WORKSPACE / art.repo_path).exists()
