from __future__ import annotations

from prometheus_client import Counter, Gauge
from sqlmodel import Session, select

from ai_org_backend.db import engine
from ai_org_backend.main import DEFAULT_BUDGET, pool
from ai_org_backend.models import Task

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


def todo_count(tenant: str) -> int:
    with Session(engine) as s:
        return (
            s.exec(select(Task).where(Task.tenant_id == tenant, Task.status == "todo"))
        ).count()


def budget_left(tenant: str) -> float:
    return float(pool.hget("budget", tenant) or DEFAULT_BUDGET)


def alert(msg: str, kind: str = "orch") -> None:
    print(f"⚠️  [{kind.upper()}] {msg}")
    PROM_ALERT_CNT.labels(kind).inc()
