from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ai_org_backend.db import SessionLocal
from ai_org_backend.metrics import prom_counter
from ai_org_backend.models import Task
from ai_org_backend.services.storage import vector_store

RETRIEVED_SNIPPETS = prom_counter(
    "ai_retrieved_snippets_total",
    "Count of artefacts snippets retrieved for context (by source)",
    ("source",),
)


def get_relevant_snippets(
    tenant_id: str,
    purpose_id: Optional[str],
    query_text: str,
    top_k: int = 3,
    scope: str = "project",
) -> List[Dict[str, str]]:
    """Retrieve relevant context snippets for a query via semantic vector search."""

    snippets: List[Dict[str, str]] = []
    if not query_text or vector_store is None:
        return snippets

    try:
        results = vector_store.query_vectors(tenant_id, query_text, top_k=top_k * 2)
    except Exception as exc:  # pragma: no cover - defensive logging
        logging.getLogger(__name__).warning("Vector search failed: %s", exc)
        return snippets

    if not results:
        return snippets

    session = None
    if purpose_id and scope != "global":
        try:
            session = SessionLocal()
        except Exception as exc:  # pragma: no cover - defensive logging
            logging.getLogger(__name__).warning("DB session init failed: %s", exc)
            session = None

    filtered = []
    for res in results:
        if scope != "global" and purpose_id and session:
            try:
                task_id = res.payload.get("task")
                task_obj = session.get(Task, task_id) if task_id else None
                if not task_obj or task_obj.purpose_id != purpose_id:
                    continue
            except Exception as exc:  # pragma: no cover - defensive logging
                logging.getLogger(__name__).warning(
                    "Purpose filter check failed for %s: %s", res.id, exc
                )
                continue
        if res.payload.get("obsolete") is True:
            continue
        filtered.append(res)

    if session:
        session.close()

    newest_by_base: Dict[str, Any] = {}
    for res in filtered:
        file_path = res.payload.get("file", "")
        fname = Path(file_path).name
        stem = Path(fname).stem
        suffix = Path(fname).suffix
        base_name = stem
        version_num = 0
        match = re.match(r"^(?P<name>.+?)_(?P<num>\d+)$", stem)
        if match:
            base_name = match.group("name")
            version_num = int(match.group("num") or 0)
        base_key = base_name + suffix
        prev = newest_by_base.get(base_key)
        if not prev or version_num > prev["ver"]:
            newest_by_base[base_key] = {"ver": version_num, "res": res}

    deduplicated_results = [entry["res"] for entry in newest_by_base.values()]
    deduplicated_results.sort(key=lambda r: getattr(r, "score", 0), reverse=True)

    seen_shas = set()
    seen_previews = set()
    for res in deduplicated_results:
        file_path = Path("workspace") / res.payload.get("file", "")
        content = ""
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            content = ""
        sha = res.payload.get("sha")
        if sha:
            if sha in seen_shas:
                continue
            seen_shas.add(sha)
        else:
            preview = content[:100]
            if preview in seen_previews:
                continue
            seen_previews.add(preview)

        snippet_text = content[:500] + ("..." if len(content) > 500 else "")
        source = res.payload.get("file", f"Artifact {res.id}")
        if source.startswith(f"{tenant_id}/"):
            source = source[len(f"{tenant_id}/"):]

        lower = source.lower()
        if any(x in lower for x in ["util", "helper"]):
            category = "Utility Functions"
        elif any(x in lower for x in ["api", "controller"]):
            category = "API Layer"
        elif lower.endswith(".md"):
            category = "Documentation"
        elif "test" in lower or lower.endswith("_test.py"):
            category = "Tests"
        else:
            category = "Code"

        RETRIEVED_SNIPPETS.labels(source=source).inc()
        snippets.append({"source": source, "chunk": snippet_text, "category": category})
        if len(snippets) >= top_k:
            break

    return snippets


__all__ = ["get_relevant_snippets"]
