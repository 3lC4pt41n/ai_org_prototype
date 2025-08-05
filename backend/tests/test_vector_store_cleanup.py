import sys
import types


def test_store_vector_removes_previous_point_and_tracks_version(monkeypatch):
    """Old vectors are removed and version incremented before storing new."""
    # stub openai embedding
    openai_stub = types.SimpleNamespace(
        Embedding=types.SimpleNamespace(
            create=lambda *a, **k: {"data": [{"embedding": [0.1]}]}
        )
    )
    import ai_org_backend.services.vector_store as vs_module
    monkeypatch.setattr(vs_module, "openai", openai_stub, raising=False)

    # minimal PointStruct substitute
    monkeypatch.setattr(
        vs_module,
        "PointStruct",
        lambda id, vector, payload: {"id": id, "vector": vector, "payload": payload},
    )

    class DummyClient:
        def __init__(self):
            self.deleted = False
            self.upsert_payload = None

        def retrieve(self, *a, **k):
            return [types.SimpleNamespace(payload={"version": 1})]

        def delete(self, *a, **k):
            self.deleted = True

        def upsert(self, *a, **k):
            self.upsert_payload = k["points"][0]["payload"]

    vs = vs_module.VectorStore()
    vs.client = DummyClient()

    vs.store_vector("tenant", "art", "hello")

    assert vs.client.deleted, "existing point should be removed"
    assert vs.client.upsert_payload["version"] == 2
    assert vs.client.upsert_payload["tenant"] == "tenant"
