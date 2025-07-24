#!/usr/bin/env python
"""
Seed Neo4j with all Tasks (inkl. KPI-Spalten) und deren Abhängigkeiten.

Usage:
    python scripts/seed_graph.py --tenant demo
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Dict

from neo4j import GraphDatabase
from sqlmodel import Session, select
from sqlalchemy.orm import selectinload

# ───── Repo-Root in sys.path aufnehmen ───────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
if ROOT.as_posix() not in sys.path:
    sys.path.insert(0, ROOT.as_posix())

from ai_org_backend.db import engine                           # noqa: E402
from ai_org_backend.models import Task, TaskDependency         # noqa: E402

# ───── Neo4j-Konfiguration ──────────────────────────────────────────
NEO4J_URL  = os.getenv("NEO4J_URL",  "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASS", "s3cr3tP@ss")

driver = GraphDatabase.driver(NEO4J_URL, auth=(NEO4J_USER, NEO4J_PASS))

CLEAN_CYPHER = "MATCH (t:Task) DETACH DELETE t"

MERGE_TASK = """
MERGE (t:Task {id:$id})
SET   t.status            = $status,
      t.desc              = $desc,
      t.business_value    = $bv,
      t.tokens_plan       = $tok_plan,
      t.tokens_actual     = $tok_act,
      t.purpose_relevance = $purp_rel
"""

MERGE_DEP = """
MATCH (a:Task {id:$from_id}), (b:Task {id:$to_id})
MERGE (a)-[r:DEPENDS_ON {kind:$kind}]->(b)
SET   r.source=$source,
      r.note=$note
"""

# ───── Ingest-Routine ───────────────────────────────────────────────
def ingest(tenant: str) -> Dict[str, int]:
    """Kopiert Tasks + Dependencies eines Tenants nach Neo4j."""
    with driver.session() as g, Session(engine) as db:
        # Neo4j leeren
        g.run(CLEAN_CYPHER)

        # Tasks dieses Tenants holen
        tasks = db.exec(
            select(Task).where(Task.tenant_id == tenant)
        ).all()

        # Dependencies inkl. beteiligter Tasks eager-laden
        deps = db.exec(
            select(TaskDependency)
            .join(Task, Task.id == TaskDependency.from_id)
            .where(Task.tenant_id == tenant)
            .options(
                selectinload(TaskDependency.from_task),
                selectinload(TaskDependency.to_task),
            )
        ).all()

        merged: set[str] = set()
        with g.begin_transaction() as tx:
            # zuerst Task-Nodes
            for t in tasks:
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

            # dann Kanten
            for dep in deps:
                tx.run(
                    MERGE_DEP,
                    from_id=dep.from_id,
                    to_id=dep.to_id,
                    kind=dep.kind.value,
                    source=dep.source,
                    note=dep.note,
                )

            tx.commit()

    driver.close()
    return {"tasks": len(merged), "deps": len(deps)}

# ───── CLI-Entry-Point ──────────────────────────────────────────────
if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Seed Neo4j graph from Task table")
    ap.add_argument("--tenant", default="demo", help="tenant_id to migrate")
    ns = ap.parse_args()

    stats = ingest(ns.tenant)
    print(
        f"✅  Seeded {stats['tasks']} tasks and {stats['deps']} dependencies "
        f"for tenant '{ns.tenant}' into Neo4j"
    )
