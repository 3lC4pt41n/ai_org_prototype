"""Celery application instance for ai_org_backend tasks."""

from ai_org_backend import config
from celery import Celery
from celery.signals import before_task_publish, task_failure, task_prerun
from dotenv import load_dotenv

# Load environment variables so configuration values are available when the
# module is imported by the Celery command line interface.
load_dotenv()


celery = Celery(__name__, broker=config.REDIS_URL, backend=config.REDIS_URL)
celery.conf.task_acks_late = True
# Route tasks dynamically based on tenant and task type
celery.conf.task_routes = ("ai_org_backend.tasks.celery_app.dynamic_router",)
celery.conf.task_create_missing_queues = True


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
        if budget_left(tenant_id) < cost_est:
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


def dynamic_router(task_name: str, args, kwargs, options, task=None, **unused):
    """Route tasks to tenant-specific queues based on tenant_id and task type."""
    if not args:
        return options
    tenant_id = args[0]
    if not isinstance(tenant_id, str):
        return options
    queue_suffix = None
    if task_name.startswith("agent."):
        if task_name in {"agent.integration", "agent.e2e"}:
            queue_suffix = "qa"
        elif task_name in {"agent.performance", "agent.security"}:
            queue_suffix = "telemetry"
        elif task_name == "agent.code_review":
            queue_suffix = "qa.review"
        elif task_name == "agent.refactor":
            queue_suffix = "qa.refactor"
        else:
            queue_suffix = "qa"
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
