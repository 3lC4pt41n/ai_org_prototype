"""S-Sprint3 Fix #11: Stuck-task watchdog as Celery Beat task.

Wraps the existing ``orchestrator.watchdog.requeue_stuck_tasks()`` logic
into a periodic Celery beat task that runs every 5 minutes.

Registered as ``watchdog.detect_stuck_tasks`` in the beat schedule
(see ``celeryconfig.CELERY_BEAT_SCHEDULE``).
"""

from __future__ import annotations

import logging

from ai_org_backend.tasks.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(
    name="watchdog.detect_stuck_tasks",
    bind=True,
    max_retries=1,
    acks_late=True,
)
def watchdog_detect_stuck_tasks(self) -> dict:
    """Periodic watchdog: detect and requeue stuck tasks for all tenants.

    For each tenant, tasks stuck in ``doing`` status with no heartbeat
    for > 15 minutes are requeued (up to 3 retries) or moved to the
    dead-letter queue.
    """
    from sqlmodel import Session, select
    from ai_org_backend.db import engine
    from ai_org_backend.models import Tenant
    from ai_org_backend.orchestrator.watchdog import requeue_stuck_tasks

    logger.info("[Watchdog-Beat] Starting stuck-task detection cycle")
    results: dict[str, int] = {}

    try:
        with Session(engine) as session:
            tenants = session.exec(select(Tenant)).all()
            tenant_ids = [t.id for t in tenants]
    except Exception as exc:
        logger.error("[Watchdog-Beat] Failed to fetch tenants: %s", exc)
        return {"error": str(exc)}

    total_requeued = 0
    for tid in tenant_ids:
        try:
            requeued = requeue_stuck_tasks(tid)
            results[tid] = requeued
            total_requeued += requeued
            if requeued:
                logger.warning(
                    "[Watchdog-Beat] Tenant %s: %d stuck tasks requeued", tid, requeued
                )
        except Exception as exc:
            logger.error("[Watchdog-Beat] Failed for tenant %s: %s", tid, exc)
            results[tid] = -1

    logger.info(
        "[Watchdog-Beat] Cycle complete: %d tenants checked, %d tasks requeued",
        len(tenant_ids),
        total_requeued,
    )
    return results
