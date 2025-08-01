from __future__ import annotations

from prometheus_client import Counter, Gauge
from sqlmodel import Session, select

from ai_org_backend.db import engine
from ai_org_backend.main import DEFAULT_BUDGET, pool
from ai_org_backend.models import Task
from ai_org_backend.models.task import TaskStatus

PROM_ALERT_CNT = Counter("ai_alerts_total", "Alerts triggered", ["type"])
PROM_TASK_BLOCKED = Gauge(
    "ai_tasks_blocked",
    "Number of blocked tasks",
    ["tenant"],
)
PROM_CRIT_PATH_LEN = Gauge(
    "ai_critical_path",
    "Length of critical path",
    ["tenant"],
)
PROM_BUDGET_BLOCKED = Gauge(
    "ai_tasks_budget_blocked",
    "Number of tasks blocked by budget",
    ["tenant"],
)
PROM_TASK_FAILED = Counter(
    "ai_tasks_failed_total",
    "Number of tasks that failed",
    ["tenant"]
)
insights_generated_total = Counter(
    "ai_insights_total",
    "Insights generated",
)


def todo_count(tenant: str) -> int:
    with Session(engine) as s:
        return (
            s.exec(select(Task).where(Task.tenant_id == tenant, Task.status == TaskStatus.TODO))
        ).count()


def budget_left(tenant: str) -> float:
    return float(pool.hget("budget", tenant) or DEFAULT_BUDGET)


def alert(msg: str, kind: str = "orch") -> None:
    print(f"⚠️  [{kind.upper()}] {msg}")
    PROM_ALERT_CNT.labels(kind).inc()
