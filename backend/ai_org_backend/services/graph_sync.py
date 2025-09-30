"""
Graph sync helpers for Neo4j.
Keeps Task nodes and dependency edges in sync with the SQL source of truth.
Idempotent MERGE/SET operations, safe to call often.
"""
from __future__ import annotations

from datetime import datetime as dt
from typing import Iterable, Optional

from ai_org_backend.db import SessionLocal
from ai_org_backend.models import Task
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
    agent_role: Optional[str] = None,
    model_name: Optional[str] = None,
    prompt_template: Optional[str] = None,
    requires_approval: Optional[bool] = None,
    pipeline_phase_id: Optional[str] = None,
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
        "agent_role": agent_role,
        "model_name": model_name,
        "prompt_template": prompt_template,
        "requires_approval": requires_approval,
        "pipeline_phase_id": pipeline_phase_id,
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


def upsert_artifact(
    task_id: str,
    sha256: str,
    *,
    status: Optional[str] = None,
    desc: Optional[str] = None,
) -> None:
    """MERGE Artifact node and PRODUCED edge for the given task."""

    task_status = status
    task_desc = desc
    if task_status is None or task_desc is None:
        with SessionLocal() as session:
            task_obj = session.get(Task, task_id)
            if task_status is None:
                task_status = str(task_obj.status) if task_obj and task_obj.status else "todo"
            if task_desc is None:
                task_desc = task_obj.description if task_obj and task_obj.description else ""
    computed_status = str(task_status) if task_status is not None else "todo"
    computed_desc = (task_desc or "")[:200]
    params = {
        "tid": task_id,
        "sha": sha256,
        "status": computed_status,
        "desc": computed_desc,
        "ts": dt.utcnow().isoformat(),
    }
    cypher = """
    MERGE (t:Task {id:$tid})
      ON CREATE SET t.status=$status, t.desc=$desc, t.created_at=$ts
    MERGE (a:Artifact {sha256:$sha})
      ON CREATE SET a.created_at=$ts
    MERGE (t)-[:PRODUCED]->(a)
    """
    with driver.session() as g:
        g.run(cypher, **params)


def remove_tasks(task_ids: Iterable[str]) -> None:
    """Detach delete all Task nodes for the provided identifiers."""

    ids = [tid for tid in task_ids if tid]
    if not ids:
        return
    cypher = """
    MATCH (t:Task)
    WHERE t.id IN $ids
    DETACH DELETE t
    """
    with driver.session() as g:
        g.run(cypher, ids=ids)
