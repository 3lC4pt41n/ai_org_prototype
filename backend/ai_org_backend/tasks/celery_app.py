"""Celery application instance for ai_org_backend tasks."""

from celery import Celery
from celery.signals import task_prerun, task_failure, before_task_publish
from dotenv import load_dotenv
from ai_org_backend import config

# Load environment variables so configuration values are available when the
# module is imported by the Celery command line interface.
load_dotenv()


celery = Celery(__name__, broker=config.REDIS_URL, backend=config.REDIS_URL)
celery.conf.task_acks_late = True


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

        from ai_org_backend.orchestrator.inspector import (
            budget_left,
            alert,
            PROM_BUDGET_BLOCKED,
        )
        from ai_org_backend.main import Repo, TOKEN_PRICE_PER_1000
        from ai_org_backend.db import SessionLocal
        from ai_org_backend.models import Task

        with SessionLocal() as session:
            task_obj = session.get(Task, t_id)
        if not task_obj:
            return

        cost_est = (task_obj.tokens_plan or 0) * (TOKEN_PRICE_PER_1000 / 1000.0)
        if budget_left(tenant_id) < cost_est:
            Repo(tenant_id).update(t_id, status="budget_exceeded", notes="budget skip")
            alert(f"Task {t_id} skipped due to insufficient budget", "budget")
            PROM_BUDGET_BLOCKED.labels(tenant_id).inc()
            # Revoke so the worker ignores the task if it still gets published
            celery.control.revoke(t_id)
    except Exception as exc:  # pragma: no cover - best effort handler
        print(f"Budget check failed: {exc}")


@task_prerun.connect
def set_task_status_doing(
    sender=None, task_id=None, task=None, args=None, kwargs=None, **extra
):
    if args and len(args) >= 2:
        tenant_id, t_id = args[0], args[1]
        try:
            from ai_org_backend.main import Repo

            Repo(tenant_id).update(t_id, status="doing")
        except Exception as e:
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
            from ai_org_backend.main import Repo

            Repo(tenant_id).update(t_id, status="failed", notes=str(exception))
            from ai_org_backend.orchestrator.inspector import PROM_TASK_FAILED

            PROM_TASK_FAILED.labels(tenant_id).inc()
        except Exception as e:
            print(f"Failed to set status 'failed' for task {t_id}: {e}")
