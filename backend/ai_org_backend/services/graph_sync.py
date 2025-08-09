"""
Graph sync helpers for Neo4j.
Keeps Task nodes and dependency edges in sync with the SQL source of truth.
Idempotent MERGE/SET operations, safe to call often.
"""
from __future__ import annotations

from typing import Optional

from ai_org_backend.services.storage import driver  # existing Neo4j driver


def _coerce_kind(kind: Optional[str]) -> str:
    """
    Normalize dependency kind. Default to FINISH_START if unknown/None.
    """
    k = (kind or "").strip().upper()
    return k if k else "FINISH_START"


def upsert_task(
    task_id: str,
    *,
    desc: Optional[str] = None,
    status: Optional[str] = None,
    business_value: Optional[float] = None,
    tokens_plan: Optional[int] = None,
    tokens_actual: Optional[int] = None,
    purpose_relevance: Optional[float] = None,
) -> None:
    """
    MERGE Task node and SET provided properties (only those not None).
    Safe to call on every DB update.
    """
    props = {
        "desc": desc,
        "status": status,
        "business_value": business_value,
        "tokens_plan": tokens_plan,
        "tokens_actual": tokens_actual,
        "purpose_relevance": purpose_relevance,
    }
    # Build SET fragment dynamically (only provided props).
    set_lines = []
    params = {"id": task_id}
    for key, value in props.items():
        if value is not None:
            set_lines.append(f"t.{key} = ${key}")
            params[key] = value

    if not set_lines:
        # nothing to update but ensure node exists
        cypher = "MERGE (t:Task {id:$id})"
        with driver.session() as g:
            g.run(cypher, **params)
        return

    cypher = f"""
    MERGE (t:Task {{id:$id}})
    SET {", ".join(set_lines)}
    """
    with driver.session() as g:
        g.run(cypher, **params)


def upsert_dependency(from_id: str, to_id: str, *, kind: Optional[str] = None) -> None:
    """
    MERGE edge (:Task {id:from})-[:DEPENDS_ON {kind:...}]->(:Task {id:to})
    """
    k = _coerce_kind(kind)
    cypher = """
    MERGE (p:Task {id:$from})
    MERGE (c:Task {id:$to})
    MERGE (p)-[r:DEPENDS_ON]->(c)
    SET r.kind = $kind
    """
    with driver.session() as g:
        g.run(cypher, **{"from": from_id, "to": to_id, "kind": k})


def remove_dependency(from_id: str, to_id: str) -> None:
    """Delete a DEPENDS_ON edge if present."""
    cypher = """
    MATCH (:Task {id:$from})-[r:DEPENDS_ON]->(:Task {id:$to})
    DELETE r
    """
    with driver.session() as g:
        g.run(cypher, **{"from": from_id, "to": to_id})
