"""Qdrant vector storage service."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ai_org_backend.config import QDRANT_API_KEY, QDRANT_URL

from . import budget

try:  # pragma: no cover - optional dependency during tests
    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        Distance,
        FieldCondition,
        Filter,
        MatchValue,
        PointStruct,
        VectorParams,
    )
except Exception:  # pragma: no cover
    QdrantClient = None  # type: ignore
    Distance = FieldCondition = Filter = MatchValue = PointStruct = VectorParams = None  # type: ignore

try:  # pragma: no cover - allow tests without openai package
    import openai
except Exception:  # pragma: no cover
    openai = None  # type: ignore


def _embedding_with_tokens(text: str) -> tuple[list[float], int]:
    """Return embedding vector and token count using OpenAI client, compatible with
    both legacy and new SDKs."""
    if openai is None:
        raise RuntimeError("openai package not available")
    if hasattr(openai, "OpenAI"):
        client = openai.OpenAI()
        resp = client.embeddings.create(model="text-embedding-3-small", input=text)
        data = resp.to_dict() if hasattr(resp, "to_dict") else resp
    elif hasattr(openai, "Embedding"):
        resp = openai.Embedding.create(model="text-embedding-3-small", input=text)
        data = resp
    elif hasattr(openai, "Embeddings"):
        resp = openai.Embeddings.create(model="text-embedding-3-small", input=text)
        data = resp
    else:  # pragma: no cover - defensive
        raise AttributeError("No embedding method found on openai module")
    vector = data["data"][0]["embedding"]
    usage = data.get("usage") or {}
    tokens = int(usage.get("total_tokens") or usage.get("prompt_tokens") or 0)
    if tokens <= 0:
        tokens = max(1, int(len(text) / 4))
    return vector, tokens


class VectorStore:
    """Wrapper around a Qdrant collection for storing embeddings."""

    def __init__(self) -> None:
        self.client: Optional["QdrantClient"] = None
        self.collection_name = "artifacts"
        if QDRANT_URL and QdrantClient is not None:
            try:
                self.client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
                if not self.client.collection_exists(self.collection_name):
                    try:
                        self.client.create_collection(
                            collection_name=self.collection_name,
                            vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
                        )
                    except Exception as exc:
                        # Falls die Collection bereits existiert (HTTP 409), Fehler ignorieren
                        if "already exists" in str(exc):
                            logging.getLogger(__name__).info(
                                "Qdrant collection '%s' already exists, skipping creation",
                                self.collection_name,
                            )
                        else:
                            raise
            except Exception as exc:  # pragma: no cover
                logging.getLogger(__name__).warning("Qdrant init failed: %s", exc)
                self.client = None

    def store_vector(
        self,
        tenant_id: str,
        artifact_id: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Embed *text* and store it in the vector database.

        Returns ``True`` on success and ``False`` if the vector could not be
        persisted. A ``False`` return value indicates that the caller should
        retry the operation.
        """

        if not self.client or not text or openai is None:
            return True
        try:
            version = 1
            existing_payload: Dict[str, Any] | None = None
            try:
                existing = self.client.retrieve(
                    collection_name=self.collection_name,
                    ids=[artifact_id],
                    with_payload=True,
                    with_vectors=False,
                )
                if existing:
                    existing_payload = existing[0].payload or {}
                    prev_version = existing_payload.get("version")
                    if isinstance(prev_version, int):
                        version = prev_version + 1
                    self.client.delete(
                        collection_name=self.collection_name,
                        points_selector=[artifact_id],
                    )
            except Exception as exc:  # pragma: no cover
                logging.getLogger(__name__).warning("Vector cleanup failed: %s", exc)

            vector, total_tokens = _embedding_with_tokens(text)
            if tenant_id:
                try:
                    budget.charge_tokens(tenant_id, "text-embedding-3-small", total_tokens)
                except budget.BudgetExceededError as exc:
                    logging.getLogger(__name__).warning(
                        "Budget exceeded for tenant %s: %s", tenant_id, exc
                    )
                    return False
            payload: Dict[str, Any] = {
                "tenant": tenant_id,
                "version": version,
                "artifact_id": artifact_id,
            }
            if metadata:
                payload.update(metadata)
                payload["version"] = int(payload.get("version", version))
            self.client.upsert(
                collection_name=self.collection_name,
                points=[PointStruct(id=artifact_id, vector=vector, payload=payload)],
            )
            return True
        except Exception as exc:  # pragma: no cover
            logging.getLogger(__name__).warning("Vector upsert failed: %s", exc)
            return False

    def query_vectors(self, tenant_id: str, query_text: str, top_k: int = 5) -> List[Any]:
        """Return up to *top_k* similar vectors for *query_text*."""

        if not self.client or openai is None:
            return []
        try:
            vector, total_tokens = _embedding_with_tokens(query_text)
            if tenant_id:
                try:
                    budget.charge_tokens(tenant_id, "text-embedding-3-small", total_tokens)
                except budget.BudgetExceededError as exc:
                    logging.getLogger(__name__).warning(
                        "Budget exceeded for tenant %s: %s", tenant_id, exc
                    )
                    return []
            q_filter = Filter(
                must=[FieldCondition(key="tenant", match=MatchValue(value=tenant_id))],
                must_not=[FieldCondition(key="obsolete", match=MatchValue(value=True))],
            )
            return self.client.search(
                collection_name=self.collection_name,
                query_vector=vector,
                limit=top_k,
                query_filter=q_filter,
            )
        except Exception as exc:  # pragma: no cover
            logging.getLogger(__name__).warning("Vector search failed: %s", exc)
            return []


__all__ = ["VectorStore"]
