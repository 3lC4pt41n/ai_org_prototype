from __future__ import annotations

from prometheus_client import Counter, Gauge
from sqlmodel import Session, func, select

from ai_org_backend.db import engine
from ai_org_backend.models import Task, TaskStatus, Tenant
from ai_org_backend.redis_client import DEFAULT_BUDGET, pool

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


def budget_left(tenant: str, purpose: str | None = None) -> float:
    """Return remaining budget for a tenant or a specific purpose."""

    with Session(engine) as s:
        tenant_obj = s.get(Tenant, tenant)

    if not tenant_obj:
        return 0.0

    # Tenant-wide budget comes from the SQL balance field.
    if not purpose:
        value = float(tenant_obj.balance)
        if value <= 0:
            PROM_BUDGET_BLOCKED.labels(tenant).set(1)
        else:
            PROM_BUDGET_BLOCKED.labels(tenant).set(0)
        return value

    # Purpose-specific budgets are tracked in Redis; fall back to default if missing.
    redis_value: float | None = None
    try:
        raw = pool.get(f"budget:{tenant}:{purpose}") if pool is not None else None
        if raw is not None:
            redis_value = float(raw)
    except Exception:
        redis_value = None

    if redis_value is not None:
        return redis_value

    # Fallback: return default project budget if nothing stored yet.
    return float(DEFAULT_BUDGET)
