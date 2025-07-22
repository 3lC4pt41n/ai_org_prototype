#!/usr/bin/env python
"""
Seed Neo4j with Task rows (incl. KPI columns).

Usage:
    python scripts/seed_graph.py --tenant demo
"""
from __future__ import annotations
import argparse
import os
import sys
import pathlib
from typing import Dict

# ── dynamic repo-root import ─────────────────────────────────────────
ROOT = pathlib.Path(__file__).resolve().parents[1]
if ROOT.as_posix() not in sys.path:
    sys.path.insert(0, ROOT.as_posix())

from sqlmodel import Session, select  # noqa: E402
from ai_org_backend.db import engine  # noqa: E402
from ai_org_backend.models import Task, TaskDependency  # noqa: E402
from sqlalchemy.orm import aliased  # noqa: E402
from neo4j import GraphDatabase  # noqa: E402

# ── config ───────────────────────────────────────────────────────────
NEO4J_URL = os.getenv("NEO4J_URL", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASS", "s3cr3tP@ss")

driver = GraphDatabase.driver(NEO4J_URL, auth=(NEO4J_USER, NEO4J_PASS))

CLEAN = "MATCH (t:Task) DETACH DELETE t"
MERGE_TASK = """
MERGE (t:Task {id:$id})
SET   t.status            = $status,
      t.desc              = $desc,
      t.business_value    = $bv,
      t.tokens_plan       = $tok_plan,
      t.tokens_actual     = $tok_act,
      t.purpose_relevance = $purp_rel
"""
DEPENDS_CYPHER = """
MATCH (a:Task {id:$from_id}), (b:Task {id:$to_id})
MERGE (a)-[r:DEPENDS_ON {kind:$kind}]->(b)
SET   r.source=$source,
      r.note=$note
"""


# ── main logic ───────────────────────────────────────────────────────
def ingest(tenant: str) -> Dict[str, int]:
    """Copy one tenant's tasks into Neo4j; return stats."""
    with driver.session() as g, Session(engine) as db:
        g.run(CLEAN)

        t_from = aliased(Task)
        t_to = aliased(Task)
        deps = db.exec(
            select(TaskDependency, t_from, t_to)
            .join(t_from, t_from.id == TaskDependency.from_id)
            .join(t_to, t_to.id == TaskDependency.to_id)
            .where(t_from.tenant_id == tenant)
        ).all()

        merged: set[str] = set()
        with g.begin_transaction() as tx:
            for dep, a, b in deps:
                for t in (a, b):
                    if t.id not in merged:
                        tx.run(
                            MERGE_TASK,
                            id=t.id,
                            status=t.status,
                            desc=t.description,
                            bv=t.business_value,
                            tok_plan=t.tokens_plan,
                            tok_act=t.tokens_actual,
                            purp_rel=t.purpose_relevance,
                        )
                        merged.add(t.id)
                tx.run(
                    DEPENDS_CYPHER,
                    from_id=dep.from_id,
                    to_id=dep.to_id,
                    kind=dep.kind.value,
                    source=dep.source,
                    note=dep.note,
                )
            tx.commit()
    driver.close()
    return {"tasks": len(merged), "deps": len(deps)}


# ── CLI ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Seed Neo4j graph from Task")
    ap.add_argument("--tenant", default="demo", help="tenant_id to migrate")
    ns = ap.parse_args()
    stats = ingest(ns.tenant)
    print(
        f"✅  Seeded {stats['tasks']} tasks and {stats['deps']} dependencies for tenant '{ns.tenant}' into Neo4j"
    )
