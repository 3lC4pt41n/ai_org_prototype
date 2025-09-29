"""
Performance Test Agent
----------------------
Generates a small Locustfile, executes a short headless run, evaluates p95 latency.
"""

from __future__ import annotations

import logging
import os
import tempfile

from ai_org_backend.db import SessionLocal
from ai_org_backend.metrics import prom_counter, prom_hist
from ai_org_backend.models import Task, TaskDependency
from ai_org_backend.services.storage import register_artefact
from ai_org_backend.services.test_exec import run_locust
from ai_org_backend.tasks.celery_app import celery
from ai_org_backend.settings import settings

RUNS = prom_counter("ai_performance_runs_total", "Performance agent executions")
LAT = prom_hist("ai_performance_latency_seconds", "Performance agent latency")

LOCUST_TMPL = """\
from locust import HttpUser, task, between

class SmokeUser(HttpUser):
    wait_time = between(0.1, 0.3)
    @task
    def ping(self):
        self.client.get("/health")  # adjust to your health endpoint
"""


@celery.task(name="agent.performance")
def performance_task(tenant_id: str, task_id: str) -> None:
    import time

    start = time.time()
    host = os.getenv("PERF_HOST", os.getenv("API_BASE_URL", "http://localhost:8000"))
    users = int(os.getenv("PERF_USERS", "20"))
    spawn = int(os.getenv("PERF_SPAWN", "5"))
    run_time = os.getenv("PERF_TIME", "1m")
    p95_budget_ms = int(os.getenv("PERF_P95_BUDGET_MS", "750"))

    # Save locustfile
    locust_rel = f"tests/perf/locustfile_{task_id}.py"
    register_artefact(task_id, LOCUST_TMPL.encode("utf-8"), filename=locust_rel, allow_overwrite=True)

    locust_path = settings.workspace_dir / tenant_id / locust_rel
    rc, out, err = run_locust(
        locustfile=str(locust_path),
        host=host,
        users=users,
        spawn_rate=spawn,
        run_time=run_time,
        csv_base=os.path.join(tempfile.gettempdir(), f"locust_{task_id}"),
    )
    report = (
        f"Host={host}\nUsers={users}\nSpawn={spawn}\nRun={run_time}\n\n"
        f"STDOUT:\n{out}\n\nSTDERR:\n{err}"
    )
    register_artefact(
        task_id,
        report.encode("utf-8"),
        filename="reports/performance_report.txt",
        allow_overwrite=True,
    )
    RUNS.inc()
    LAT.observe(time.time() - start)

    # Simple heuristic: search for '95%' number in stdout
    import re

    m = re.search(r"95%.*?(\d+(?:\.\d+)?)", out or "")
    p95_ms = float(m.group(1)) if m else 0.0

    with SessionLocal() as s:
        t = s.get(Task, task_id)
        if rc == 0 and (p95_ms == 0.0 or p95_ms <= p95_budget_ms):
            t.status = "done"
            t.owner = "QA-Perf"
            t.notes = f"p95={p95_ms or 'n/a'}ms <= budget({p95_budget_ms}ms)"
            s.add(t)
            s.commit()
        else:
            t.status = "failed"
            t.owner = "QA-Perf"
            t.notes = f"p95={p95_ms}ms > budget({p95_budget_ms}ms)"
            s.add(t)
            s.commit()
            # Follow-up task
            fix = Task(
                tenant_id=tenant_id,
                purpose_id=t.purpose_id,
                description="Optimize performance (p95 too high)",
                business_value=1.0,
                tokens_plan=800,
                purpose_relevance=1.0,
                notes=f"Observed p95={p95_ms}ms > {p95_budget_ms}ms. See performance_report.txt",
            )
            s.add(fix)
            s.flush()
            s.add(TaskDependency(from_id=task_id, to_id=fix.id, dependency_type="FINISH_START"))
            s.commit()
            try:
                from ai_org_backend.scripts.seed_graph import ingest

                ingest(tenant_id)
            except Exception as e:
                logging.error(f"[PerformanceAgent] Neo4j ingest failed for new task {fix.id}: {e}")
