"""S2-04 / S2-05 / S2-06: Stuck-task detector, dead-letter queue, and heartbeat.

The *watchdog* runs as a periodic task (Celery beat or inline in the
orchestrator loop) and:

1. **Detects stuck tasks** (S2-04): any task in ``doing`` status whose
   ``last_heartbeat_at`` exceeds a configurable threshold is considered stuck.

2. **Dead-letter queue** (S2-05): tasks that have exhausted their retry budget
   or failed with an unrecoverable error are moved to ``dead_letter`` status.

3. **Heartbeat receiver** (S2-06): workers call ``record_heartbeat()`` at
   regular intervals while processing a task.  This updates
   ``Task.last_heartbeat_at`` so the watchdog can distinguish between
   genuinely stuck and still-running tasks.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime as dt, timedelta

from prometheus_client import Counter, Gauge
from sqlalchemy import update
from sqlmodel import Session, select

from ai_org_backend.db import engine
from ai_org_backend.models import Task, TaskStatus
from ai_org_backend.redis_client import pool

logger = logging.getLogger(__name__)

# ── Configuration ──
STUCK_THRESHOLD_S = 900     # 15 min without heartbeat → stuck
DLQ_MAX_RETRIES = 3         # after this many retries → dead letter
HEARTBEAT_KEY_TTL = 1800    # Redis heartbeat key expires after 30 min

# ── Prometheus metrics ──
PROM_STUCK_DETECTED = Counter(
    "ai_stuck_tasks_detected_total",
    "Tasks detected as stuck and requeued",
    ["tenant"],
)
PROM_DLQ_TASKS = Gauge(
    "ai_dlq_tasks",
    "Tasks in dead-letter queue",
    ["tenant"],
)
PROM_HEARTBEAT_RECEIVED = Counter(
    "ai_heartbeats_received_total",
    "Worker heartbeats received",
    ["tenant"],
)


# ──────────────────────────────────────────────────────────────────────
# S2-06: Worker heartbeat
# ──────────────────────────────────────────────────────────────────────

def record_heartbeat(tenant_id: str, task_id: str) -> None:
    """Called by workers to signal that a task is still being processed.

    Updates both the SQL ``last_heartbeat_at`` column and a fast Redis key
    so the watchdog can check liveness without hitting the database every time.
    """
    now = dt.utcnow()

    # Fast path: Redis heartbeat (checked first by the watchdog)
    if pool is not None:
        try:
            pool.set(
                f"heartbeat:{tenant_id}:{task_id}",
                str(now.timestamp()),
                ex=HEARTBEAT_KEY_TTL,
            )
        except Exception as exc:
            logger.debug("Redis heartbeat write failed for task %s: %s", task_id, exc)

    # Slow path: SQL heartbeat (authoritative)
    try:
        with Session(engine) as session:
            session.exec(  # type: ignore[call-overload]
                update(Task)
                .where(Task.id == task_id)
                .values(last_heartbeat_at=now)
            )
            session.commit()
    except Exception as exc:
        logger.warning("SQL heartbeat update failed for task %s: %s", task_id, exc)

    PROM_HEARTBEAT_RECEIVED.labels(tenant_id).inc()


def _last_heartbeat_ts(tenant_id: str, task_id: str) -> float | None:
    """Return the latest heartbeat timestamp (epoch) for a task.

    Checks Redis first for speed, falls back to the SQL column.
    """
    # Try Redis
    if pool is not None:
        try:
            raw = pool.get(f"heartbeat:{tenant_id}:{task_id}")
            if raw:
                return float(raw)
        except Exception:
            pass

    # Fall back to SQL
    try:
        with Session(engine) as session:
            task = session.get(Task, task_id)
            if task and task.last_heartbeat_at:
                return task.last_heartbeat_at.timestamp()
    except Exception:
        pass

    return None


# ──────────────────────────────────────────────────────────────────────
# S2-04: Stuck-task detector
# ──────────────────────────────────────────────────────────────────────

def detect_stuck_tasks(tenant_id: str, threshold_s: int = STUCK_THRESHOLD_S) -> list[str]:
    """Find tasks in ``doing`` status with no recent heartbeat.

    Returns a list of task IDs that are considered stuck.
    """
    cutoff = dt.utcnow() - timedelta(seconds=threshold_s)
    stuck_ids: list[str] = []

    with Session(engine) as session:
        doing_tasks = session.exec(
            select(Task).where(
                Task.tenant_id == tenant_id,
                Task.status == TaskStatus.DOING,
            )
        ).all()

        for task in doing_tasks:
            # Check heartbeat (Redis first, then SQL column, then created_at)
            last_ts = _last_heartbeat_ts(tenant_id, task.id)
            if last_ts is None:
                # No heartbeat ever recorded – use created_at
                last_ts = task.created_at.timestamp()

            if last_ts < cutoff.timestamp():
                stuck_ids.append(task.id)

    return stuck_ids


def requeue_stuck_tasks(tenant_id: str, threshold_s: int = STUCK_THRESHOLD_S) -> int:
    """Detect and requeue stuck tasks.  Returns the number of requeued tasks."""
    stuck_ids = detect_stuck_tasks(tenant_id, threshold_s)
    if not stuck_ids:
        return 0

    requeued = 0
    with Session(engine) as session:
        for task_id in stuck_ids:
            task = session.get(Task, task_id)
            if not task:
                continue

            if task.retries >= DLQ_MAX_RETRIES:
                # S2-05: Move to dead-letter queue
                _move_to_dlq(session, task, "Max retries exceeded after stuck detection")
                continue

            task.status = "todo"
            task.retries += 1
            task.last_heartbeat_at = None
            base_note = (task.notes or "").split("| stuck-requeue")[0].strip()
            task.notes = f"{base_note} | stuck-requeue {task.retries}/{DLQ_MAX_RETRIES}"
            task.version += 1
            session.add(task)
            requeued += 1
            PROM_STUCK_DETECTED.labels(tenant_id).inc()
            logger.warning(
                "Task %s detected as stuck – requeued (retry %d/%d)",
                task_id, task.retries, DLQ_MAX_RETRIES,
            )

            # Clean up Redis heartbeat key
            if pool is not None:
                try:
                    pool.delete(f"heartbeat:{tenant_id}:{task_id}")
                except Exception:
                    pass

        session.commit()

    return requeued


# ──────────────────────────────────────────────────────────────────────
# S2-05: Dead-letter queue
# ──────────────────────────────────────────────────────────────────────

def _move_to_dlq(session: Session, task: Task, reason: str) -> None:
    """Move a task to the dead-letter queue (terminal failure state)."""
    task.status = "dead_letter"
    task.version += 1
    base_note = (task.notes or "").split("| DLQ:")[0].strip()
    task.notes = f"{base_note} | DLQ: {reason}"
    session.add(task)
    logger.error(
        "Task %s moved to dead-letter queue: %s", task.id, reason
    )


def move_to_dlq(task_id: str, reason: str) -> None:
    """Public API: move a task to DLQ by ID."""
    with Session(engine) as session:
        task = session.get(Task, task_id)
        if not task:
            logger.warning("Cannot move non-existent task %s to DLQ", task_id)
            return
        _move_to_dlq(session, task, reason)
        session.commit()

    # Update Prometheus metrics
    if task:
        _refresh_dlq_gauge(task.tenant_id)


def get_dlq_tasks(tenant_id: str) -> list[Task]:
    """Return all tasks in the dead-letter queue for a tenant."""
    with Session(engine) as session:
        return list(session.exec(
            select(Task).where(
                Task.tenant_id == tenant_id,
                Task.status == "dead_letter",
            )
        ).all())


def retry_dlq_task(task_id: str) -> bool:
    """Manually retry a task from the dead-letter queue (admin action).

    Returns True if the task was successfully requeued.
    """
    with Session(engine) as session:
        task = session.get(Task, task_id)
        if not task or task.status != "dead_letter":
            return False

        task.status = "todo"
        task.retries = 0
        task.version += 1
        task.last_heartbeat_at = None
        base_note = (task.notes or "").split("| DLQ:")[0].strip()
        task.notes = f"{base_note} | manual-retry from DLQ"
        session.add(task)
        session.commit()
        logger.info("Task %s manually retried from DLQ", task_id)

    return True


def _refresh_dlq_gauge(tenant_id: str) -> None:
    """Update the Prometheus DLQ gauge for a tenant."""
    try:
        with Session(engine) as session:
            from sqlmodel import func
            count = session.exec(
                select(func.count(Task.id)).where(
                    Task.tenant_id == tenant_id,
                    Task.status == "dead_letter",
                )
            ).one()
        PROM_DLQ_TASKS.labels(tenant_id).set(count)
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────────────
# Orchestrator integration: periodic watchdog call
# ──────────────────────────────────────────────────────────────────────

def run_watchdog(tenant_id: str) -> None:
    """Run a single watchdog cycle.  Called from the orchestrator loop."""
    requeued = requeue_stuck_tasks(tenant_id)
    _refresh_dlq_gauge(tenant_id)
    if requeued:
        logger.info("[Watchdog] Requeued %d stuck task(s) for tenant %s", requeued, tenant_id)
