from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

from ai_org_backend.db import SessionLocal
from ai_org_backend.models import Task
from ai_org_backend.services.storage import vector_store


def get_relevant_snippets(
    tenant_id: str,
    purpose_id: Optional[str],
    query_text: str,
    top_k: int = 3,
) -> List[Dict[str, str]]:
    """Retrieve relevant context snippets for a query via semantic vector search.

    This function performs a semantic search using the shared ``vector_store``. The
    returned list contains dictionaries with ``source`` and ``chunk`` keys. This is
    designed as part of the long‑term memory retrieval for tasks and can be
    extended for more advanced retrieval strategies.

    Args:
        tenant_id: Identifier for isolating vector search results per tenant.
        purpose_id: Optional purpose/project identifier to further filter results.
        query_text: The text to search for similar content.
        top_k: Number of top results to retrieve.

    Returns:
        A list of snippet dictionaries. If no results are found or the vector
        search fails, an empty list is returned.
    """

    snippets: List[Dict[str, str]] = []
    if not query_text or vector_store is None:
        return snippets

    try:
        results = vector_store.query_vectors(tenant_id, query_text, top_k=top_k)
    except Exception as exc:  # pragma: no cover - defensive logging
        logging.getLogger(__name__).warning("Vector search failed: %s", exc)
        return snippets

    session = None
    if purpose_id:
        try:
            session = SessionLocal()
        except Exception as exc:  # pragma: no cover - defensive logging
            logging.getLogger(__name__).warning("DB session init failed: %s", exc)
            session = None

    for result in results:
        if purpose_id and session:
            try:
                task_id = result.payload.get("task")
                if task_id:
                    task_obj = session.get(Task, task_id)
                    if not task_obj or task_obj.purpose_id != purpose_id:
                        continue
                else:
                    continue
            except Exception as exc:  # pragma: no cover - defensive logging
                logging.getLogger(__name__).warning(
                    "Purpose filter check failed for result %s: %s", result.id, exc
                )
                continue

        file_path = Path("workspace") / result.payload.get("file", "")
        snippet_text = ""
        if file_path.exists():
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                content = ""
            snippet_text = content[:500] + ("..." if len(content) > 500 else "")

        source = result.payload.get("file", f"Artifact {result.id}")
        if source and source.startswith(f"{tenant_id}/"):
            source = source[len(f"{tenant_id}/"):]

        snippets.append({"source": source, "chunk": snippet_text})

    if session:
        session.close()

    return snippets


__all__ = ["get_relevant_snippets"]

