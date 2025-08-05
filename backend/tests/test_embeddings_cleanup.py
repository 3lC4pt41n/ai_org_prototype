import sys
import types
from types import SimpleNamespace
from sqlmodel import SQLModel, Session


def test_overwrite_vector_cleanup(monkeypatch, tmp_path):
    """When overwriting an artifact, old vectors are marked obsolete and new vector persists."""
    # Stub OpenAI embedding API
    openai_stub = types.ModuleType("openai")
    openai_stub.Embedding = SimpleNamespace(create=lambda *args, **kwargs: {"data": [{"embedding": [0.0]}]})
    openai_stub.OpenAIError = Exception
    monkeypatch.setitem(sys.modules, "openai", openai_stub)

    # Stub Qdrant client and models
    qc_stub = types.ModuleType("qdrant_client")
    qc_models_stub = types.ModuleType("qdrant_client.models")

    class DummyQdrantClient:
        def __init__(self, *args, **kwargs):
            self.store = {}

        def collection_exists(self, name):
            return True

        def create_collection(self, *args, **kwargs):
            return None

        def retrieve(self, collection_name, ids, **kwargs):
            if ids and ids[0] in self.store:
                return [SimpleNamespace(payload=self.store[ids[0]])]
            return []

        def upsert(self, collection_name, points, **kwargs):
            # Store payload by point id
            for point in points:
                self.store[point.id] = point.payload

        def delete(self, collection_name, points_selector=None, **kwargs):
            # Not used in this test but required by VectorStore.store_vector
            pass

        def set_payload(self, collection_name, points_selector=None, payload=None, **kwargs):
            if payload is None or points_selector is None:
                return
            flt = getattr(points_selector, "filter", points_selector)
            conditions = {}
            for cond in getattr(flt, "must", []):
                conditions[cond.key] = cond.match.value
            for pid, pl in self.store.items():
                if all(pl.get(k) == v for k, v in conditions.items()):
                    pl.update(payload)

    qc_stub.QdrantClient = DummyQdrantClient

    # Minimal dummy model classes
    qc_models_stub.Distance = SimpleNamespace(COSINE="COSINE")
    qc_models_stub.VectorParams = lambda **kwargs: None
    qc_models_stub.PointStruct = lambda id, vector, payload: SimpleNamespace(id=id, payload=payload)
    qc_models_stub.Filter = lambda must: SimpleNamespace(must=must)
    qc_models_stub.FieldCondition = lambda key, match: SimpleNamespace(key=key, match=match)
    qc_models_stub.MatchValue = lambda value: SimpleNamespace(value=value)
    qc_models_stub.FilterSelector = lambda filter: SimpleNamespace(filter=filter)

    monkeypatch.setitem(sys.modules, "qdrant_client", qc_stub)
    monkeypatch.setitem(sys.modules, "qdrant_client.models", qc_models_stub)

    # Ensure QDRANT_URL is set so that VectorStore will attempt to initialize the Qdrant client
    monkeypatch.setenv("QDRANT_URL", "http://localhost")
    monkeypatch.setenv("QDRANT_API_KEY", "")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test.db")

    # Import storage after stubbing dependencies
    import importlib

    monkeypatch.delitem(sys.modules, "ai_org_backend.db", raising=False)
    monkeypatch.delitem(sys.modules, "ai_org_backend.config", raising=False)
    monkeypatch.delitem(sys.modules, "ai_org_backend.services.storage", raising=False)
    storage = importlib.import_module("ai_org_backend.services.storage")

    # Monkeypatch Neo4j and git commit functions to no-ops
    storage._link_neo4j = lambda *args, **kwargs: None
    storage._git_commit = lambda *args, **kwargs: None
    storage.WORKSPACE = tmp_path / "ws"
    storage.WORKSPACE.mkdir()
    storage.vector_store.client = DummyQdrantClient()

    # Initialize an in-memory database and create a dummy task
    SQLModel.metadata.create_all(storage.engine)
    with Session(storage.engine) as session:
        from ai_org_backend.models import Task

        session.add(Task(id="t1", tenant_id="demo", description="Demo task", status="done"))
        session.commit()

    # Create an initial artifact and embed it
    file1 = tmp_path / "demo.txt"
    file1.write_text("Version one content " * 10)
    art1 = storage.register_artefact("t1", file1)

    # Overwrite the artifact with new content
    file2 = tmp_path / "new.txt"
    file2.write_text("Version two content " * 10)
    art2 = storage.register_artefact("t1", file2, filename="demo.txt", allow_overwrite=True)

    # Both artifacts have the same repo_path since overwrite succeeded
    assert art2.repo_path == art1.repo_path

    # After overwrite, old vector remains but is flagged obsolete, new one persists
    vs_client = storage.vector_store.client
    assert art1.id in vs_client.store
    assert vs_client.store[art1.id].get("obsolete") is True
    assert art2.id in vs_client.store
    assert vs_client.store[art2.id].get("obsolete") is not True

    # The new vector's payload should reflect the updated metadata
    new_payload = vs_client.store[art2.id]
    assert new_payload.get("tenant") == "demo"
    assert new_payload.get("file") == art2.repo_path
    assert new_payload.get("sha")
    # The version should reset to 1 for the new artifact (new artifact_id used)
    assert new_payload.get("version") == 1

