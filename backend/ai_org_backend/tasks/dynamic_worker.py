import os
import time

from ai_org_backend.db import SessionLocal
from ai_org_backend.models import Tenant
from ai_org_backend.tasks.celery_app import celery
from dotenv import load_dotenv

load_dotenv()


def launch_worker(queue_groups: list[str]):
    """Launch a Celery worker consuming the given queue groups for all tenants."""
    retries = 5
    while retries:
        try:
            with SessionLocal() as session:
                tenants = session.query(Tenant).all()
                tenant_ids = [t.id for t in tenants]
            break
        except Exception as exc:  # pragma: no cover - startup retry
            retries -= 1
            print(f"[dynamic_worker] DB connection failed, retrying... ({exc})")
            time.sleep(5)
    else:
        tenant_ids = []
        print("[dynamic_worker] Warning: No tenants found or DB unreachable.")

    queues: list[str] = []
    for tenant in tenant_ids or [""]:
        for suffix in queue_groups:
            if tenant:
                queues.append(f"{tenant}:{suffix}")
            else:
                queues.append("celery")
    queue_list = ",".join(queues)
    print(f"[dynamic_worker] Starting worker for queues: {queue_list}")
    celery.worker_main(
        [
            "worker",
            "--loglevel=INFO",
            "--pool=solo",
            "--queues",
            queue_list,
        ]
    )


if __name__ == "__main__":
    role_group = os.environ.get("WORKER_GROUP")
    if role_group == "architect":
        launch_worker(["architect"])
    elif role_group == "insight":
        launch_worker(["insight"])
    elif role_group == "reviewer":
        launch_worker(["reviewer"])
    else:
        launch_worker(["dev", "qa", "ux_ui", "telemetry", "reviewer"])
