from __future__ import annotations

import asyncio
import time

from sqlmodel import Session, select

from ai_org_backend.main import celery
from ai_org_backend.orchestrator.graph_orchestrator import (
    TENANT,
    seed_if_empty,
    cypher,
    LEAF_Q,
    BLOCKED_Q,
    CRIT_Q,
)
from ai_org_backend.models import Task, TaskDependency
from ai_org_backend.orchestrator.router import classify_role
from ai_org_backend.orchestrator.inspector import (
    alert,
    budget_left,
    todo_count,
    PROM_TASK_BLOCKED,
    PROM_CRIT_PATH_LEN,
)


def _ready_for_execution(task: Task, session: Session) -> bool:
    """Return True if a task has no unresolved prerequisites."""
    unresolved = (
        session.exec(
            select(TaskDependency)
            .where(TaskDependency.to_id == task.id)
            .join(Task, Task.id == TaskDependency.from_id)
            .where(Task.status != "done")
        ).first()
    )
    return unresolved is None


async def orchestrator() -> None:
    last = time.time()
    while True:
        seed_if_empty()
        for rec in cypher(LEAF_Q):
            role = classify_role(rec["d"])
            celery.send_task(
                f"agent.{role}", args=[TENANT, rec["id"]], queue=f"{TENANT}:{role}"
            )
        if time.time() - last > 10:
            blocked = cypher(BLOCKED_Q)[0]["blocked"]
            crit = cypher(CRIT_Q)
            PROM_TASK_BLOCKED.labels(TENANT).set(blocked)
            if crit:
                PROM_CRIT_PATH_LEN.labels(TENANT).set(crit[0]["l"])
            print(
                f"ℹ️ todo:{todo_count(TENANT):>3} "
                f"blocked:{blocked:<2} "
                f"budget:{budget_left(TENANT):.2f}$"
            )
            last = time.time()
        if budget_left(TENANT) < 1:
            alert("Budget exhausted", "budget")
        await asyncio.sleep(2)

