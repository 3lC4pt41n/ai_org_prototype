from __future__ import annotations

import asyncio
import logging
import time

from sqlmodel import Session, func, select

from ai_org_backend.db import engine
from ai_org_backend.main import (
    BUDGET_GA,
    DEFAULT_BUDGET,
    TOKEN_PRICE_PER_1000,
    Repo,
    budget_left,
    celery,
    debit,
    pool,
)
from ai_org_backend.models import Artifact, Purpose, Task, TaskDependency, TaskStatus
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
    todo_count,
)
from ai_org_backend.orchestrator.router import classify_role

# ╭────────────────── Retry settings ──────────────────╮
MAX_RETRIES = 2  # total automatic attempts
RETRY_DELAY_S = 30  # wait 30s after fail before retry


def _retry_failed_tasks() -> None:
    """Requeue failed tasks that have remaining retries."""
    now = time.time()
    with Session(engine) as db:
        q = select(Task).where(Task.status == "failed", Task.retries < MAX_RETRIES)
        for t in db.exec(q):
            age = now - t.created_at.timestamp()
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


def _generate_plan_for_purpose(purpose_id: str) -> None:
    """Generate initial architecture and task plan for a new Purpose."""
    from ai_org_backend.agents.architect import run_architect
    from ai_org_backend.agents.planner import run_planner
    from ai_org_backend.main import Repo
    from ai_org_backend.scripts.seed_graph import ingest
    from ai_org_backend.services.storage import save_artefact

    # Load the Purpose and run Architect agent to get blueprint
    with Session(engine) as db_session:
        purpose = db_session.get(Purpose, purpose_id)
        if not purpose:
            alert(f"Purpose {purpose_id} not found for planning", "orchestrator")
            return
    try:
        blueprint_md = run_architect(purpose)
    except Exception as e:
        alert(f"Orchestrator: Architect failed for purpose {purpose_id}: {e}", "error")
        return

    # Save the architecture blueprint as a completed task with artefact
    with Session(engine) as db_session:
        blueprint_task = Task(
            tenant_id=TENANT,
            purpose_id=purpose_id,
            description="Architecture Blueprint",
            status="done",
        )
        db_session.add(blueprint_task)
        db_session.commit()
        db_session.refresh(blueprint_task)
        save_artefact(
            blueprint_task.id,
            blueprint_md.encode("utf-8"),
            filename="blueprints/architecture_blueprint.md",
            media_type="text/markdown",
            allow_overwrite=True,
        )
        Repo(TENANT).update(blueprint_task.id, owner="Architect", notes="Blueprint completed")

    # Run Planner agent to generate implementation task list
    try:
        tasks_plan = run_planner(blueprint_md)
    except Exception as e:
        alert(f"Orchestrator: Planner failed for purpose {purpose_id}: {e}", "error")
        return
    if not isinstance(tasks_plan, list):
        alert("Planner returned no task list", "warn")
        return

    # Insert planned tasks into the database (status='todo')
    with Session(engine) as db_session:
        for t in tasks_plan:
            task_obj = Task(
                tenant_id=TENANT,
                purpose_id=purpose_id,
                description=t.get("description", ""),
                business_value=float(t.get("business_value", 1.0)),
                tokens_plan=int(t.get("tokens_plan", 0)),
                purpose_relevance=float(t.get("purpose_relevance", 0.0)),
                status="todo",
            )
            db_session.add(task_obj)
        db_session.commit()

    # Mark PRD artefact as released (approved) once planning is done
    with Session(engine) as db_session:
        prd_task = db_session.exec(
            select(Task).where(
                Task.purpose_id == purpose_id,
                Task.description.ilike("Product Requirements Document"),
            )
        ).first()
        if prd_task:
            prd_artifact = db_session.exec(
                select(Artifact).where(Artifact.task_id == prd_task.id)
            ).first()
            if prd_artifact:
                prd_artifact.released = True
                db_session.add(prd_artifact)
                db_session.commit()

    try:
        ingest(TENANT)
    except Exception as e:
        alert(f"Orchestrator: ingest failed for purpose {purpose_id}: {e}", "warn")


async def orchestrator() -> None:
    last = time.time()
    LAST_DONE_COUNT = 0
    near_budget_alert_sent = False
    alerted_fail_modules: set[str] = set()
    alerted_retry_modules: set[str] = set()
    # ⏳ Initiales Seeden der Backlogs (PRD und Architektur-Blueprint generieren)
    await asyncio.to_thread(seed_if_empty)

    while True:
        # No global budget check here; budgets are managed per-purpose
        # 1️⃣ retry failed tasks
        _retry_failed_tasks()
        if pool.get(f"pause:{TENANT}"):
            await asyncio.sleep(2)
            continue

        # 2️⃣ Check for new Purposes to plan (Planner now invoked by Orchestrator)
        with Session(engine) as session:
            purposes = session.exec(
                select(Purpose).where(Purpose.tenant_id == TENANT, Purpose.is_active)
            ).all()
            purpose_to_process = None
            for p in purposes:
                # Skip if this purpose is individually paused
                if pool.get(f"pause:{TENANT}:{p.id}"):
                    continue
                prd_task = session.exec(
                    select(Task).where(
                        Task.purpose_id == p.id,
                        Task.description.ilike("Product Requirements Document"),
                        Task.status == TaskStatus.DONE,
                    )
                ).first()
                blueprint_task = session.exec(
                    select(Task).where(
                        Task.purpose_id == p.id, Task.description == "Architecture Blueprint"
                    )
                ).first()
                next_task = session.exec(
                    select(Task)
                    .where(Task.purpose_id == p.id, Task.status != TaskStatus.DONE)
                    .where(
                        Task.description != "Product Requirements Document",
                        Task.description != "Architecture Blueprint",
                        Task.description != "Architecture & Domain Review",
                    )
                ).first()
                if prd_task and not blueprint_task and not next_task:
                    if p.mode == "manual":
                        # In manual mode, wait for user approval (PRD artefact released)
                        prd_art = session.exec(
                            select(Artifact).where(Artifact.task_id == prd_task.id)
                        ).first()
                        if not prd_art or not prd_art.released:
                            continue
                    purpose_to_process = p
                    break
        if purpose_to_process:
            try:
                await asyncio.to_thread(_generate_plan_for_purpose, purpose_to_process.id)
            except Exception as e:
                alert(
                    f"Orchestrator: planning failed for purpose {purpose_to_process.id}: {e}",
                    "error",
                )
            continue

        # Iterate over ready tasks
        for rec in cypher(LEAF_Q):
            # Fetch full task details for tokens_plan
            with Session(engine) as session:
                task_obj = session.get(Task, rec["id"])
            if not task_obj:
                continue
            # Skip if this purpose is paused
            if task_obj.purpose_id and pool.get(f"pause:{TENANT}:{task_obj.purpose_id}"):
                continue
            # Calculate cost estimate for this task
            cost_est = (task_obj.tokens_plan or 0) * (TOKEN_PRICE_PER_1000 / 1000.0)
            # Check purpose-specific budget
            budget_val = budget_left(TENANT, task_obj.purpose_id)
            if budget_val < cost_est:
                Repo(TENANT).update(task_obj.id, status="budget_exceeded", notes="budget skip")
                alert(f"Task {task_obj.id} skipped due to insufficient budget", "budget")
                continue
            role = classify_role(rec["d"])
            Repo(TENANT).update(task_obj.id, status="doing")
            # Deduct budget for the purpose
            debit(TENANT, cost_est, task_obj.purpose_id)
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
                    select(func.count(Task.id)).where(
                        Task.tenant_id == TENANT, Task.status == TaskStatus.BUDGET_EXCEEDED
                    )
                ).one()
            PROM_BUDGET_BLOCKED.labels(TENANT).set(budget_blocked)
            print(
                f"ℹ️ todo:{todo_count(TENANT):>3} "
                f"blocked:{blocked:<2} "
                f"budget_blocked:{budget_blocked:<2} budget:{budget_left(TENANT):.2f}$"
            )
            last = time.time()
            # Anomaly detection: alert on high failure or retry rates
            with Session(engine) as session:
                for owner in ["Dev", "UX/UI", "QA"]:
                    total = session.exec(
                        select(func.count(Task.id)).where(
                            Task.tenant_id == TENANT,
                            Task.owner == owner,
                            Task.status.in_(["done", "failed"]),
                        )
                    ).one()
                    fails = session.exec(
                        select(func.count(Task.id)).where(
                            Task.tenant_id == TENANT,
                            Task.owner == owner,
                            Task.status == "failed",
                        )
                    ).one()
                    retries = session.exec(
                        select(func.count(Task.id)).where(
                            Task.tenant_id == TENANT,
                            Task.owner == owner,
                            Task.status == "done",
                            Task.retries > 0,
                        )
                    ).one()
                    if (
                        total >= 5
                        and fails / total > 0.3
                        and fails >= 3
                        and owner not in alerted_fail_modules
                    ):
                        alert(
                            f"High failure rate in {owner} tasks: {fails} of {total} failed",
                            "warn",
                        )
                        alerted_fail_modules.add(owner)
                    if retries >= 3 and owner not in alerted_retry_modules:
                        alert(
                            f"Frequent retries in {owner} tasks: "
                            f"{retries} tasks needed multiple attempts",
                            "warn",
                        )
                        alerted_retry_modules.add(owner)
            if (
                budget_left(TENANT) < DEFAULT_BUDGET * 0.1
                and budget_left(TENANT) > 0
                and not near_budget_alert_sent
            ):
                alert(
                    f"Budget low: only ${budget_left(TENANT):.2f} remaining",
                    "warn",
                )
                near_budget_alert_sent = True
        done_count = 0
        with Session(engine) as session:
            done_count = session.exec(
                select(func.count(Task.id)).where(
                    Task.tenant_id == TENANT, Task.status == TaskStatus.DONE
                )
            ).one()
        if done_count - LAST_DONE_COUNT >= 10:
            celery.send_task("agent.project_manager", args=[TENANT], queue=f"{TENANT}:qa")
            celery.send_task("agent.adjust_plan", args=[TENANT], queue=f"{TENANT}:qa")
            LAST_DONE_COUNT = done_count
        if budget_left(TENANT) < 1:
            alert("Budget exhausted", "budget")
        await asyncio.sleep(2)


if __name__ == "__main__":
    import os
    import sys

    # Alembic-Initialisierung: Falls Migrations-Ordner fehlt, mit Hinweis abbrechen
    if not (
        os.path.isdir(os.path.join(os.getcwd(), "alembic"))
        or os.path.isdir(os.path.join(os.path.dirname(__file__), os.pardir, "alembic"))
    ):
        print("Alembic folder missing – please run 'alembic init alembic' to create it.")
        sys.exit(1)
    import asyncio

    # Früh prüfen: ist der OpenAI-Key vorhanden?
    key_present = bool(
        os.getenv("OPENAI_API_KEY")
        or os.getenv("OPENAI_KEY")
        or os.getenv("OPENAI_APIKEY")
        or os.getenv("OPENAI_API_KEY_FILE")
        or os.getenv("OPENAI_API_KEY_B64")
    )
    from ai_org_backend.services.llm_client import ensure_client

    if not key_present:
        print("⚠️  [ORCH] No OPENAI_API_KEY found; LLM-Funktionen werden übersprungen.")
    else:
        try:
            ensure_client()
        except Exception as e:
            print(f"⚠️  [ORCH] OpenAI-Client-Init fehlgeschlagen (weiter ohne LLM): {e}")

    # Ensure Neo4j index on Task.status exists (to avoid UnknownPropertyKeyWarning)
    from ai_org_backend.orchestrator.graph_orchestrator import driver

    try:
        with driver.session() as session:
            session.run("CREATE INDEX IF NOT EXISTS FOR (t:Task) ON (t.status)")
            print("ℹ️ Ensured Neo4j index on Task(status) exists")
    except Exception as e:
        logging.error("Failed to create Neo4j index for Task(status): %s", e)
    asyncio.run(orchestrator())
