from __future__ import annotations

import asyncio
import logging
import time

from ai_org_backend.db import engine
from ai_org_backend.main import (  # import orchestrator dependencies
    BUDGET_GA,
    TOKEN_PRICE_PER_1000,
    Repo,
    celery,
)
from ai_org_backend.models import Task, TaskDependency
from ai_org_backend.models.task import TaskStatus
from ai_org_backend.orchestrator.graph_orchestrator import (
    BLOCKED_Q,
    CRIT_Q,
    LEAF_Q,
    TENANT,
    cypher,
    seed_if_empty,
)
from ai_org_backend.orchestrator.inspector import (
    PROM_BUDGET_BLOCKED,
    PROM_CRIT_PATH_LEN,
    PROM_TASK_BLOCKED,
    alert,
    budget_left,
    todo_count,
)
from ai_org_backend.orchestrator.router import classify_role
from sqlmodel import Session, select

# ╭────────────────── Retry settings ──────────────────╮
MAX_RETRIES = 2  # total automatic attempts
RETRY_DELAY_S = 30  # wait 30s after fail before retry


def _retry_failed_tasks() -> None:
    """Requeue failed tasks that have remaining retries."""
    now = time.time()
    with Session(engine) as db:
        q = select(Task).where(Task.status == "failed", Task.retries < MAX_RETRIES)
        for t in db.exec(q):
            age = now - t.updated_at.timestamp()
            if age < RETRY_DELAY_S:
                continue

            t.status = "todo"
            t.retries += 1
            base_note = (t.notes or "").split("| auto-retry")[0].strip()
            retry_msg = f"auto-retry {t.retries}/{MAX_RETRIES}"
            t.notes = f"{base_note} | {retry_msg}" if base_note else retry_msg
            db.add(t)
            logging.info(f"Orchestrator: Task {t.id} requeued for retry {t.retries}/{MAX_RETRIES}")
        db.commit()


def _ready_for_execution(task: Task, session: Session) -> bool:
    """Return True if a task has no unresolved prerequisites."""
    unresolved = session.exec(
        select(TaskDependency)
        .where(TaskDependency.to_id == task.id)
        .join(Task, Task.id == TaskDependency.from_id)
        .where(Task.status != TaskStatus.DONE)
    ).first()
    return unresolved is None


async def orchestrator() -> None:
    last = time.time()
    while True:
        # Pre-dispatch budget availability check
        try:
            avail_budget = budget_left(TENANT)
        except Exception:
            avail_budget = 0.0  # Redis down, treat as no budget
        if avail_budget < 0:
            avail_budget = 0.0
        seed_if_empty()
        # 1️⃣ retry failed tasks
        _retry_failed_tasks()

        # Iterate over ready tasks
        for rec in cypher(LEAF_Q):
            # Fetch full task details for tokens_plan
            with Session(engine) as session:
                task_obj = session.get(Task, rec["id"])
            if not task_obj:
                continue
            # Calculate cost estimate for this task
            cost_est = (task_obj.tokens_plan or 0) * (TOKEN_PRICE_PER_1000 / 1000.0)
            if avail_budget < cost_est:
                # Skip task due to insufficient budget
                Repo(TENANT).update(task_obj.id, status="budget_exceeded", notes="budget skip")
                alert(f"Task {task_obj.id} skipped due to insufficient budget", "budget")
                continue
            # Deduct planned cost from available budget and dispatch
            avail_budget -= cost_est
            role = classify_role(rec["d"])
            Repo(TENANT).update(task_obj.id, status="doing")
            celery.send_task(f"agent.{role}", args=[TENANT, rec["id"]], queue=f"{TENANT}:{role}")
        if time.time() - last > 10:
            blocked = cypher(BLOCKED_Q)[0]["blocked"]
            crit = cypher(CRIT_Q)
            PROM_TASK_BLOCKED.labels(TENANT).set(blocked)
            if crit:
                PROM_CRIT_PATH_LEN.labels(TENANT).set(crit[0]["l"])
            # Update Prometheus metrics for budget
            BUDGET_GA.labels(TENANT).set(budget_left(TENANT))
            # Count tasks skipped due to budget
            budget_blocked = 0
            with Session(engine) as session:
                budget_blocked = session.exec(
                    select(Task).where(
                        Task.tenant_id == TENANT, Task.status == TaskStatus.BUDGET_EXCEEDED
                    )
                ).count()
            PROM_BUDGET_BLOCKED.labels(TENANT).set(budget_blocked)
            print(
                f"ℹ️ todo:{todo_count(TENANT):>3} "
                f"blocked:{blocked:<2} "
                f"budget_blocked:{budget_blocked:<2} budget:{budget_left(TENANT):.2f}$"
            )
            last = time.time()
        if budget_left(TENANT) < 1:
            alert("Budget exhausted", "budget")
        await asyncio.sleep(2)


if __name__ == "__main__":
    import asyncio

    asyncio.run(orchestrator())
