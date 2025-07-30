"""Celery application instance for ai_org_backend tasks."""

from celery import Celery
from celery.signals import task_prerun, task_failure
from dotenv import load_dotenv
from ai_org_backend import config

# Load environment variables so configuration values are available when the
# module is imported by the Celery command line interface.
load_dotenv()


celery = Celery(__name__, broker=config.REDIS_URL, backend=config.REDIS_URL)
celery.conf.task_acks_late = True


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
def set_task_status_failed(sender=None, task_id=None, exception=None, args=None, kwargs=None, einfo=None, **extra):
    if args and len(args) >= 2:
        tenant_id, t_id = args[0], args[1]
        try:
            from ai_org_backend.main import Repo
            Repo(tenant_id).update(t_id, status="failed", notes=str(exception))
            from ai_org_backend.orchestrator.inspector import PROM_TASK_FAILED
            PROM_TASK_FAILED.labels(tenant_id).inc()
        except Exception as e:
            print(f"Failed to set status 'failed' for task {t_id}: {e}")

