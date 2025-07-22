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
from ai_org_backend.db import engine
from ai_org_backend.main import Task
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
MERGE_EDGE = """
MATCH (a:Task {id:$from_id}), (b:Task {id:$to_id})
MERGE (a)-[:DEPENDS_ON]->(b)
"""


# ── main logic ───────────────────────────────────────────────────────
def ingest(tenant: str) -> Dict[str, int]:
    """Copy one tenant's tasks into Neo4j; return stats."""
    with driver.session() as g, Session(engine) as db:
        g.run(CLEAN)
        rows = db.exec(select(Task).where(Task.tenant_id == tenant)).all()
        for row in rows:
            g.run(
                MERGE_TASK,
                id=row.id,
                status=row.status,
<<<<<<< HEAD
=======
                val=row.business_value,
>>>>>>> ed9b63776adb94a0f28bb1b16f1ae1e68da7063a
                desc=row.description,
                bv=row.business_value,
                tok_plan=row.tokens_plan,
                tok_act=row.tokens_actual,
                purp_rel=row.purpose_relevance,
            )
            if row.depends_on:
                g.run(MERGE_EDGE, from_id=row.id, to_id=row.depends_on)
    return {"tasks": len(rows)}


# ── CLI ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Seed Neo4j graph from Task")
    ap.add_argument("--tenant", default="demo", help="tenant_id to migrate")
    ns = ap.parse_args()
    stats = ingest(ns.tenant)
    print(f"✅  Seeded {stats['tasks']} tasks for tenant '{ns.tenant}' into Neo4j")