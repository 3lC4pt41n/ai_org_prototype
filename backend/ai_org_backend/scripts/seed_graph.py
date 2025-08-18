from __future__ import annotations

import logging
import os
from typing import Dict

from ai_org_backend.db import engine
from ai_org_backend.models import Artifact, Task, TaskDependency
from neo4j import GraphDatabase
from sqlalchemy.orm import selectinload
from sqlmodel import Session, select

logger = logging.getLogger(__name__)

# ───── Neo4j-Konfiguration ──────────────────────────────────────────
NEO4J_URL = os.getenv("NEO4J_URL", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASS = os.getenv("NEO4J_PASS")
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
"""


# ───── Ingest-Routine ───────────────────────────────────────────────
def ingest(tenant: str) -> Dict[str, int]:
    """Kopiert Tasks + Dependencies eines Tenants nach Neo4j."""
    logger.info("Starting Neo4j ingest for tenant '%s'", tenant)
    with driver.session() as g, Session(engine) as db:
        # Neo4j leeren
        g.run(CLEAN_CYPHER)

        # Tasks dieses Tenants holen
        tasks = db.exec(select(Task).where(Task.tenant_id == tenant)).all()

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
        # Alle Artefakte dieses Tenants holen (für PRODUCED-Kanten)
        artifacts = db.exec(select(Artifact).where(Artifact.task.has(tenant_id=tenant))).all()

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

            # dann Kanten (Task-Dependencies)
            for dep in deps:
                tx.run(
                    MERGE_DEP,
                    from_id=dep.from_id,
                    to_id=dep.to_id,
                    kind=getattr(dep, "dependency_type", "blocks"),
                )
            # dann Artefakt-Kanten (Task->Artifact)
            for art in artifacts:
                tx.run(
                    """
                    MERGE (a:Artifact {sha256:$sha})
                      ON CREATE SET a.created_at=$ts
                    MATCH (t:Task {id:$tid})
                    MERGE (t)-[:PRODUCED]->(a)
                    """,
                    sha=art.sha256,
                    ts=art.created_at.isoformat(),
                    tid=art.task_id,
                )

            tx.commit()

    driver.close()
    logger.info(
        "Neo4j ingest complete: %d tasks and %d dependencies ingested for tenant '%s'",
        len(merged),
        len(deps),
        tenant,
    )
    return {"tasks": len(merged), "deps": len(deps)}
