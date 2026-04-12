"""Celery application instance for ai_org_backend tasks."""

from celery import Celery
from celery.signals import before_task_publish, task_failure, task_prerun, task_success
from celery.exceptions import SoftTimeLimitExceeded
from dotenv import load_dotenv

from ai_org_backend import config

# Load environment variables so configuration values are available when the
# module is imported by the Celery command line interface.
load_dotenv()  # load .env so config values (REDIS_URL, etc.) are set


# Initialize Celery app with a clear name and broker/backend config
celery = Celery("ai_org_backend", broker=config.REDIS_URL, backend=config.REDIS_URL)
celery.conf.task_acks_late = True
celery.conf.task_default_queue = "celery"
# Route tasks dynamically based on tenant and task type
celery.conf.task_routes = ("ai_org_backend.tasks.celery_app.dynamic_router",)
celery.conf.task_create_missing_queues = True

# ── S1-07: Global Task Timeouts ──
from ai_org_backend.celeryconfig import TASK_SOFT_TIME_LIMIT, TASK_TIME_LIMIT
celery.conf.task_soft_time_limit = TASK_SOFT_TIME_LIMIT
celery.conf.task_time_limit = TASK_TIME_LIMIT

# ── S1-11: Redis Broker Resilience ──
celery.conf.broker_transport_options = {
    "visibility_timeout": 3600,  # 1 hour - tasks redelivered if not acked
    "retry_policy": {
        "timeout": 5.0,          # connection timeout in seconds
        "max_retries": 5,        # retry up to 5 times on connection failure
        "interval_start": 0.2,   # initial retry delay
        "interval_step": 0.5,    # increase delay by this much each retry
        "interval_max": 5.0,     # max delay between retries
    },
    "socket_keepalive": True,
}
celery.conf.broker_connection_retry_on_startup = True
# Alias the Celery app as `app` for Celery CLI autodiscovery
app = celery

celery.autodiscover_tasks(packages=["ai_org_backend.agents"])
celery.conf.include = [
    "ai_org_backend.agents.vision",
    "ai_org_backend.agents.architect",
    "ai_org_backend.agents.architect_feedback",
    "ai_org_backend.agents.planner",
    "ai_org_backend.agents.reviewer",
    "ai_org_backend.agents.product_owner",
    "ai_org_backend.agents.agent_dev",
    "ai_org_backend.agents.agent_qa",
    "ai_org_backend.agents.agent_ux_ui",
    "ai_org_backend.agents.agent_insight",
    "ai_org_backend.agents.agent_integration",
    "ai_org_backend.agents.repo_composer",
    "ai_org_backend.tasks.llm_tasks",
    "ai_org_backend.tasks.watchdog_task",
]


@before_task_publish.connect
def enforce_budget(sender=None, body=None, headers=None, **extra):
    """Prevent tasks from being queued if tenant budget is exhausted."""
    try:
        args = []
        if isinstance(body, dict) and "args" in body:
            args = body.get("args", [])
        elif isinstance(body, (list, tuple)):
            # Protocol v1 passes a tuple (args, kwargs, embed)
            if body and isinstance(body[0], (list, tuple)):
                args = list(body[0])
            else:
                args = list(body)
        if len(args) < 2:
            return
        tenant_id, t_id = args[0], args[1]

        from ai_org_backend.db import SessionLocal
        from ai_org_backend.main import TOKEN_PRICE_PER_1000, Repo
        from ai_org_backend.models import Task
        from ai_org_backend.orchestrator.inspector import PROM_BUDGET_BLOCKED, alert, budget_left

        with SessionLocal() as session:
            task_obj = session.get(Task, t_id)
        if not task_obj:
            return

        cost_est = (task_obj.tokens_plan or 0) * (TOKEN_PRICE_PER_1000 / 1000.0)
        if budget_left(tenant_id, task_obj.purpose_id) < cost_est:
            Repo(tenant_id).update(t_id, status="budget_exceeded", notes="budget skip")
            alert(f"Task {t_id} skipped due to insufficient budget", "budget")
            PROM_BUDGET_BLOCKED.labels(tenant_id).inc()
            # Revoke so the worker ignores the task if it still gets published
            celery.control.revoke(t_id)
    except Exception as exc:  # pragma: no cover - best effort handler
        print(f"Budget check failed: {exc}")


@task_prerun.connect
def set_task_status_doing(sender=None, task_id=None, task=None, args=None, kwargs=None, **extra):
    if args and len(args) >= 2:
        tenant_id, t_id = args[0], args[1]
        try:
            from ai_org_backend.db import SessionLocal
            from ai_org_backend.models import Task as TaskModel
            from sqlmodel import select
            from datetime import datetime as dt

            with SessionLocal() as session:
                task_obj = session.get(TaskModel, t_id)
                if not task_obj:
                    return

                # S1-09: Idempotency check - skip if task already completed or has artifacts
                if task_obj.status in ("done", "cancelled", "skipped", "budget_exceeded", "dead_letter"):
                    print(f"[idempotency] Task {t_id} already in terminal state '{task_obj.status}', revoking duplicate execution")
                    # Revoke THIS specific execution to prevent double-processing
                    if hasattr(sender, 'request') and sender.request:
                        sender.request.callbacks = None
                    raise Exception(f"Idempotency violation: task {t_id} already {task_obj.status}")

                task_obj.status = "doing"
                task_obj.version += 1  # S2-03: Increment version on status change
                task_obj.last_heartbeat_at = dt.utcnow()  # S2-06: Initial heartbeat
                session.add(task_obj)
                session.commit()

            # S2-06: Record initial heartbeat in Redis
            try:
                from ai_org_backend.orchestrator.watchdog import record_heartbeat
                record_heartbeat(tenant_id, t_id)
            except Exception:
                pass  # Best effort – Redis might be temporarily unavailable

        except Exception as e:
            if "Idempotency violation" in str(e):
                raise  # Re-raise idempotency violations
            print(f"Failed to set status 'doing' for task {t_id}: {e}")


@task_failure.connect
def set_task_status_failed(
    sender=None,
    task_id=None,
    exception=None,
    args=None,
    kwargs=None,
    einfo=None,
    **extra,
):
    if args and len(args) >= 2:
        tenant_id, t_id = args[0], args[1]
        try:
            from ai_org_backend.db import SessionLocal
            from ai_org_backend.main import Repo
            from ai_org_backend.models import Task as TaskModel

            if isinstance(exception, SoftTimeLimitExceeded):
                notes = f"Task timed out after soft limit ({TASK_SOFT_TIME_LIMIT}s)"
            else:
                notes = str(exception)

            # S2-05: Check if task should go to DLQ (max retries exhausted)
            with SessionLocal() as session:
                task_obj = session.get(TaskModel, t_id)
                if task_obj and task_obj.retries >= 3:  # DLQ_MAX_RETRIES
                    from ai_org_backend.orchestrator.watchdog import move_to_dlq
                    move_to_dlq(t_id, f"Max retries exhausted: {notes}")
                    from ai_org_backend.orchestrator.inspector import PROM_TASK_FAILED
                    PROM_TASK_FAILED.labels(tenant_id).inc()
                    return

            Repo(tenant_id).update(t_id, status="failed", notes=notes)
            from ai_org_backend.orchestrator.inspector import PROM_TASK_FAILED
            PROM_TASK_FAILED.labels(tenant_id).inc()
        except Exception as e:
            print(f"Failed to set status 'failed' for task {t_id}: {e}")


@task_success.connect
def check_fix_task_re_review(
    sender=None, result=None, args=None, kwargs=None, **extra
):
    """S-Sprint2 Fix #13: After a task completes successfully, check if it was
    a review fix task. If all fix tasks for the parent review are now done,
    automatically dispatch a re-review via ``dispatch_re_review()``.
    """
    if not args or len(args) < 2:
        return
    tenant_id, t_id = args[0], args[1]
    try:
        from ai_org_backend.db import SessionLocal
        from ai_org_backend.models import Task as TaskModel
        from ai_org_backend.models import TaskDependency
        from sqlmodel import select

        with SessionLocal() as session:
            task_obj = session.get(TaskModel, t_id)
            if not task_obj:
                return

            # Only proceed if this looks like a review fix task
            desc = (task_obj.description or "").strip()
            if not desc.startswith("Review Fix:"):
                return

            # Find the review task(s) this fix task blocks
            deps = session.exec(
                select(TaskDependency).where(TaskDependency.from_id == t_id)
            ).all()

            for dep in deps:
                review_task = session.get(TaskModel, dep.to_id)
                if not review_task:
                    continue
                # Verify it's actually a review task
                review_desc = (review_task.description or "").strip().lower()
                if "review" not in review_desc:
                    continue

                # Check if ALL fix tasks for this review are now complete
                from ai_org_backend.services.review_gate import (
                    check_fix_tasks_complete,
                    dispatch_re_review,
                )

                if check_fix_tasks_complete(review_task.id):
                    dispatched = dispatch_re_review(review_task.id, tenant_id)
                    if dispatched:
                        print(
                            f"[S2-#13] All fix tasks done for review {review_task.id}"
                            f" – re-review dispatched"
                        )
                    else:
                        print(
                            f"[S2-#13] All fix tasks done for review {review_task.id}"
                            f" – re-review NOT dispatched (escalated or error)"
                        )
    except Exception as exc:
        print(f"[S2-#13] check_fix_task_re_review failed for task {t_id}: {exc}")


def dynamic_router(task_name: str, args, kwargs, options, task=None, **unused):
    """Route tasks to tenant-specific queues based on tenant_id and task type."""
    if not args:
        return options
    tenant_id = args[0]
    if not isinstance(tenant_id, str):
        return options
    queue_suffix = None
    if task_name.startswith("agent."):
        # Route agent tasks to queue '<tenant_id>:<role>'
        queue_suffix = task_name.split(".", 1)[1]
    elif "insight" in task_name:
        queue_suffix = "insight"
    elif "architect" in task_name:
        queue_suffix = "architect"
    elif task_name.startswith("ai_org_backend.tasks.llm_tasks"):
        if task_name.endswith("dev_agent"):
            queue_suffix = "dev"
        elif task_name.endswith("ux_ui_agent"):
            queue_suffix = "ux_ui"
    if queue_suffix:
        options["queue"] = f"{tenant_id}:{queue_suffix}"
    return options
