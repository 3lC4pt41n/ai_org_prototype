"""Qdrant vector storage service."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ai_org_backend.config import QDRANT_API_KEY, QDRANT_URL

try:  # pragma: no cover - optional dependency during tests
    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        Distance,
        VectorParams,
        PointStruct,
        Filter,
        FieldCondition,
        MatchValue,
    )
except Exception:  # pragma: no cover
    QdrantClient = None  # type: ignore

try:  # pragma: no cover - allow tests without openai package
    import openai
except Exception:  # pragma: no cover
    openai = None  # type: ignore


class VectorStore:
    """Wrapper around a Qdrant collection for storing embeddings."""

    def __init__(self) -> None:
        self.client: Optional["QdrantClient"] = None
        self.collection_name = "artifacts"
        if QDRANT_URL and QdrantClient is not None:
            try:
                self.client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
                if not self.client.collection_exists(self.collection_name):
                    self.client.create_collection(
                        collection_name=self.collection_name,
                        vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
                    )
            except Exception as exc:  # pragma: no cover
                logging.getLogger(__name__).warning("Qdrant init failed: %s", exc)
                self.client = None

    def store_vector(
        self,
        tenant_id: str,
        artifact_id: str,
        text: str,
        metadata: Optional[Dict[str, str]] = None,
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

            embed = openai.Embedding.create(model="text-embedding-3-small", input=text)
            vector = embed["data"][0]["embedding"]
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
            embed = openai.Embedding.create(model="text-embedding-3-small", input=query_text)
            vector = embed["data"][0]["embedding"]
            q_filter = Filter(must=[FieldCondition(key="tenant", match=MatchValue(value=tenant_id))])
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

