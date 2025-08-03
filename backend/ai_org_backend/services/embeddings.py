from __future__ import annotations

import logging
import os
from typing import List, Sequence

from qdrant_client import QdrantClient, models

try:  # Optional dependency
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-small")
VECTOR_DIM = int(os.getenv("EMBED_DIM", "1536"))

qdrant = QdrantClient(url=QDRANT_URL)


def chunk_text(text: str, max_tokens: int = 200) -> List[str]:
    """Naively split text into chunks of roughly `max_tokens` words."""
    words = text.split()
    chunks: List[str] = []
    buf: List[str] = []
    for w in words:
        buf.append(w)
        if len(buf) >= max_tokens:
            chunks.append(" ".join(buf))
            buf = []
    if buf:
        chunks.append(" ".join(buf))
    return chunks


def embed_text(text: str) -> List[float]:
    """Return an embedding vector for `text`.
    Falls back to a zero-vector if OpenAI isn't configured."""
    if not text.strip():
        return [0.0] * VECTOR_DIM
    if OpenAI is None or not os.getenv("OPENAI_API_KEY"):
        return [0.0] * VECTOR_DIM
    try:  # pragma: no cover - network call
        client = OpenAI()
        resp = client.embeddings.create(model=EMBED_MODEL, input=text)
        return resp.data[0].embedding
    except Exception as e:  # pragma: no cover
        logging.error(f"Embedding failed: {e}")
        return [0.0] * VECTOR_DIM


def ensure_collection_exists(name: str) -> None:
    """Create the collection in Qdrant if missing."""
    try:
        qdrant.get_collection(name)
    except Exception:  # pragma: no cover - creates collection
        try:
            qdrant.recreate_collection(
                collection_name=name,
                vectors_config=models.VectorParams(
                    size=VECTOR_DIM, distance=models.Distance.COSINE
                ),
            )
        except Exception as e:
            logging.error(f"Failed to create collection '{name}': {e}")


def store_embedding_chunks(task: "Task", artefact: "Artifact", text: str) -> None:
    """Chunk, embed and store artefact text in Qdrant."""
    if not text.strip():
        return
    collection = f"{task.tenant_id}_{task.purpose_id or 'default'}"
    ensure_collection_exists(collection)
    chunks = chunk_text(text)
    points: List[models.PointStruct] = []
    for idx, chunk in enumerate(chunks):
        vec = embed_text(chunk)
        points.append(
            models.PointStruct(
                id=f"{artefact.id}#{idx}",
                vector=vec,
                payload={
                    "chunk": chunk,
                    "source": artefact.repo_path,
                    "task_id": artefact.task_id,
                },
            )
        )
    try:  # pragma: no cover - network call
        qdrant.upsert(collection_name=collection, points=points)
    except Exception as e:
        logging.error(f"Qdrant upsert failed: {e}")


def get_relevant_snippets(
    tenant_id: str, purpose_id: str | None, query_text: str, top_k: int = 5
) -> List[dict]:
    """Retrieve relevant snippets from Qdrant for a query."""
    collection = f"{tenant_id}_{purpose_id or 'default'}"
    try:
        ensure_collection_exists(collection)
        query_vec = embed_text(query_text)
        hits = qdrant.search(collection_name=collection, query_vector=query_vec, limit=top_k)
    except Exception as e:  # pragma: no cover - network call
        logging.error(f"Qdrant search failed: {e}")
        return []
    snippets = []
    for h in hits:
        payload = h.payload or {}
        chunk = payload.get("chunk")
        if chunk:
            snippets.append({"content": chunk, "source": payload.get("source")})
    return snippets

__all__ = [
    "chunk_text",
    "embed_text",
    "ensure_collection_exists",
    "store_embedding_chunks",
    "get_relevant_snippets",
]
