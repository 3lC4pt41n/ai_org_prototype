"""S3-13 / S3-14: Graph sync as Celery task with retry + periodic reconciliation.

Provides:

- ``sync_graph_task``: Celery task to incrementally sync SQL → Neo4j for a tenant.
  Includes automatic retry with exponential backoff (max 3 attempts).
- ``reconcile_graph_task``: Periodic Celery beat task that performs a full
  reconciliation between SQL source-of-truth and Neo4j.
"""

from __future__ import annotations

import logging
from datetime import datetime as dt

from ai_org_backend.tasks.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(
    name="graph.sync",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=120,
    max_retries=3,
    retry_jitter=True,
    acks_late=True,
)
def sync_graph_task(self, tenant_id: str) -> dict:
    """S3-13: Incrementally sync SQL tasks/deps/artifacts to Neo4j.

    Uses the existing ``ingest()`` function but wrapped in a Celery task
    with automatic retry and backoff.
    """
    logger.info("[GraphSync] Starting sync for tenant %s (attempt %d)", tenant_id, self.request.retries + 1)
    try:
        from ai_org_backend.scripts.seed_graph import ingest
        result = ingest(tenant_id)
        logger.info(
            "[GraphSync] Sync complete for tenant %s: %d tasks, %d deps",
            tenant_id, result.get("tasks", 0), result.get("deps", 0),
        )
        return result
    except Exception as exc:
        logger.error("[GraphSync] Sync failed for tenant %s: %s", tenant_id, exc)
        raise


@celery.task(
    name="graph.reconcile",
    bind=True,
    max_retries=1,
    acks_late=True,
)
def reconcile_graph_task(self) -> dict:
    """S3-14: Full reconciliation of SQL vs Neo4j for all tenants.

    This is designed to be called by Celery beat at a regular interval
    (e.g. every 30 minutes) to catch any drift between SQL and Neo4j.
    """
    from sqlmodel import Session, select
    from ai_org_backend.db import engine
    from ai_org_backend.models import Tenant

    logger.info("[GraphReconcile] Starting full reconciliation")
    results: dict[str, dict] = {}

    try:
        with Session(engine) as session:
            tenants = session.exec(select(Tenant)).all()
            tenant_ids = [t.id for t in tenants]
    except Exception as exc:
        logger.error("[GraphReconcile] Failed to fetch tenants: %s", exc)
        return {"error": str(exc)}

    for tid in tenant_ids:
        try:
            from ai_org_backend.scripts.seed_graph import ingest
            result = ingest(tid)
            results[tid] = result
            logger.info(
                "[GraphReconcile] Tenant %s: %d tasks, %d deps synced",
                tid, result.get("tasks", 0), result.get("deps", 0),
            )
        except Exception as exc:
            logger.error("[GraphReconcile] Failed for tenant %s: %s", tid, exc)
            results[tid] = {"error": str(exc)}

    logger.info("[GraphReconcile] Reconciliation complete for %d tenants", len(tenant_ids))
    return results


# ── Celery beat schedule entry (for use in celeryconfig.py) ──
GRAPH_RECONCILE_SCHEDULE = {
    "graph-reconcile-every-30min": {
        "task": "graph.reconcile",
        "schedule": 1800.0,  # every 30 minutes
    }
}
