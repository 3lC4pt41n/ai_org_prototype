from __future__ import annotations

from prometheus_client import Counter, Gauge
from sqlmodel import Session, func, select

from ai_org_backend.db import engine
from ai_org_backend.models import Task, TaskStatus, Tenant

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
PROM_TASK_FAILED = Counter("ai_tasks_failed_total", "Number of tasks that failed", ["tenant"])
PROM_TASK_TODO = Gauge(
    "ai_tasks_todo",
    "Number of tasks pending",
    ["tenant"],
)
insights_generated_total = Counter(
    "ai_insights_total",
    "Insights generated",
)


def todo_count(tenant: str) -> int:
    with Session(engine) as s:
        cnt = s.exec(
            select(func.count(Task.id)).where(
                Task.tenant_id == tenant, Task.status == TaskStatus.TODO
            )
        ).one()
    PROM_TASK_TODO.labels(tenant).set(cnt)
    return cnt


def alert(msg: str, kind: str = "orch") -> None:
    print(f"⚠️  [{kind.upper()}] {msg}")
    PROM_ALERT_CNT.labels(kind).inc()


def budget_left(tenant: str) -> float:
    """Gibt das verbleibende Budget für einen Tenant zurück."""
    with Session(engine) as s:
        t = s.get(Tenant, tenant)
        if not t:
            return 0.0
        value = float(t.balance)
        # optional: Metrik setzen
        if value <= 0:
            PROM_BUDGET_BLOCKED.labels(tenant).set(1)
        else:
            PROM_BUDGET_BLOCKED.labels(tenant).set(0)
        return value
