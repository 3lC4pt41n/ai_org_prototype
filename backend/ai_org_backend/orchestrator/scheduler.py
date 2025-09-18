from __future__ import annotations

import asyncio
import logging
import time

from sqlalchemy import not_
from sqlmodel import Session, func, select

from ai_org_backend.db import engine
from ai_org_backend.main import (
    BUDGET_GA,
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

MAX_RETRIES = 2
RETRY_DELAY_S = 30


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
    unresolved = session.exec(
        select(TaskDependency)
        .where(TaskDependency.to_id == task.id)
        .join(Task, Task.id == TaskDependency.from_id)
        .where(Task.status != TaskStatus.DONE)
    ).first()
    return unresolved is None


def _generate_plan_for_purpose(purpose_id: str) -> None:
    from ai_org_backend.agents.architect import run_architect
    from ai_org_backend.scripts.seed_graph import ingest
    from ai_org_backend.services.storage import save_artefact

    with Session(engine) as db_session:
        purpose = db_session.get(Purpose, purpose_id)
        if not purpose:
            alert(f"Purpose {purpose_id} not found for planning", "orchestrator")
            return
        tenant_id = purpose.tenant_id
        blueprint_task = db_session.exec(
            select(Task).where(
                Task.purpose_id == purpose_id,
                func.lower(Task.description) == "architecture blueprint",
            )
        ).first()
        review_task = db_session.exec(
            select(Task).where(
                Task.purpose_id == purpose_id,
                func.lower(Task.description) == "architecture & domain review",
            )
        ).first()

    # Decide whether to run Planner (nur wenn Review freigegeben ist)
    if (
        blueprint_task
        and blueprint_task.status == TaskStatus.DONE
        and review_task
        and review_task.status == TaskStatus.DONE
    ):
        logging.info(
            "[Orchestrator] Review approved for purpose %s – triggering Planner...",
            purpose_id,
        )
        # Dispatch Planner agent asynchronously to generate follow-up tasks
        if pool.get(f"plan_pending:{tenant_id}:{purpose_id}"):
            logging.info(
                "[Orchestrator] Planner already triggered for purpose %s – skipping duplicate",
                purpose_id,
            )
            return

        pool.set(f"plan_pending:{tenant_id}:{purpose_id}", "1", ex=300)
        try:
            celery.send_task(
                "agent.planner",
                args=[tenant_id, purpose_id],
                queue=f"{tenant_id}:planner",
            )
            logging.info("[Orchestrator] Planner agent dispatched for purpose %s", purpose_id)
        except Exception as e:
            msg = f"Orchestrator: Failed to dispatch planner for purpose {purpose_id}: {e}"
            alert(msg, "error")
            logging.error(msg)
        return
    if blueprint_task and blueprint_task.status == TaskStatus.DONE:
        logging.debug(
            "[Orchestrator] Waiting: blueprint=%s review=%s for purpose %s",
            blueprint_task.status if blueprint_task else None,
            review_task.status if review_task else None,
            purpose_id,
        )
        return

    # Run Architect to generate architecture blueprint and initial tasks
    try:
        blueprint_md = run_architect(purpose)
    except Exception as e:
        msg = f"Orchestrator: Architect failed for purpose {purpose_id}: {e}"
        alert(msg, "error")
        logging.error(msg)
        return
    blueprint_task_id = ""
    with Session(engine) as db_session:
        existing_bp = db_session.exec(
            select(Task).where(
                Task.purpose_id == purpose_id,
                func.lower(Task.description) == "architecture blueprint",
            )
        ).first()
        if existing_bp:
            blueprint_task = existing_bp
            blueprint_task.status = "done"
            db_session.add(blueprint_task)
            db_session.commit()
            db_session.refresh(blueprint_task)
            blueprint_task_id = blueprint_task.id
            logging.info("[Orchestrator] Re-using existing Architecture Blueprint task %s", blueprint_task_id)
        else:
            blueprint_task = Task(
                tenant_id=tenant_id,
                purpose_id=purpose_id,
                description="Architecture Blueprint",
                status="done",
            )
            db_session.add(blueprint_task)
            db_session.commit()
            db_session.refresh(blueprint_task)
            blueprint_task_id = blueprint_task.id
            logging.info("[Orchestrator] Created new Architecture Blueprint task %s", blueprint_task_id)
        save_artefact(
            blueprint_task_id,
            blueprint_md.encode("utf-8"),
            filename="blueprints/architecture_blueprint.md",
            media_type="text/markdown",
            allow_overwrite=True,
        )
        Repo(tenant_id).update(blueprint_task_id, owner="Architect", notes="Blueprint completed")

    # Mark PRD artifact as released (safety check)
    with Session(engine) as db_session:
        prd_task = db_session.exec(
            select(Task).where(
                Task.purpose_id == purpose_id,
                func.lower(Task.description) == "product requirements document",
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
        ingest(tenant_id)
    except Exception as e:
        alert(f"Orchestrator: ingest failed for purpose {purpose_id}: {e}", "warn")


async def orchestrator() -> None:
    last = time.time()

    await asyncio.to_thread(seed_if_empty)

    while True:
        _retry_failed_tasks()
        if pool.get(f"pause:{TENANT}"):
            await asyncio.sleep(2)
            continue

        # 2️⃣ Check purposes
        purpose_to_process: tuple[Purpose, str] | None = None
        try:
            with Session(engine) as session:
                purposes = session.exec(
                    select(Purpose).where(Purpose.tenant_id == TENANT, Purpose.is_active)
                ).all()
                for p in purposes:
                    logging.info(f"[Orchestrator] Check purpose {p.id} ({p.name}) mode={p.mode}")
                    if pool.get(f"pause:{TENANT}:{p.id}"):
                        logging.info("[Orchestrator]  → paused → skip")
                        continue

                    tasks = session.exec(select(Task).where(Task.purpose_id == p.id)).all()
                    prd_task = next(
                        (
                            t
                            for t in tasks
                            if t.description
                            and t.description.lower() == "product requirements document"
                            and t.status == TaskStatus.DONE
                        ),
                        None,
                    )
                    blueprint_task = next(
                        (t for t in tasks if t.description == "Architecture Blueprint"),
                        None,
                    )
                    prd_art = None
                    if prd_task:
                        prd_art = session.exec(
                            select(Artifact).where(Artifact.task_id == prd_task.id)
                        ).first()
                    impl_todo = next(
                        (
                            t
                            for t in tasks
                            if t.status != TaskStatus.DONE
                            and t.description
                            not in [
                                "Product Requirements Document",
                                "Architecture Blueprint",
                                "Architecture & Domain Review",
                            ]
                        ),
                        None,
                    )
                    logging.info(
                        f"[Orchestrator]  → prd_done={bool(prd_task)} "
                        f"released={getattr(prd_art,'released',None)} "
                        f"blueprint={bool(blueprint_task)} impl_todo={bool(impl_todo)}"
                    )
                    if prd_task and prd_art and prd_art.released and not blueprint_task:
                        purpose_to_process = (p, "architect")
                        break

                    review_task = next(
                        (
                            t
                            for t in tasks
                            if t.description
                            and t.description.lower() == "architecture & domain review"
                        ),
                        None,
                    )

                    if (
                        blueprint_task
                        and blueprint_task.status == TaskStatus.DONE
                        and review_task
                        and review_task.status == TaskStatus.DONE
                        and impl_todo is None
                    ):
                        purpose_to_process = (p, "planner")
                        break
        except Exception as e:
            logging.error("[Orchestrator] Failed to poll purposes: %s", e)

        if purpose_to_process:
            p, action = purpose_to_process
            if action == "architect":
                logging.info(
                    "[Orchestrator] Approved PRD for purpose %s -> start Architect",
                    p.id,
                )
            else:
                logging.info(
                    "[Orchestrator] Blueprint review approved for purpose %s -> trigger Planner",
                    p.id,
                )
            try:
                await asyncio.to_thread(_generate_plan_for_purpose, p.id)
            except Exception as e:
                alert(f"Orchestrator: planning failed for purpose {p.id}: {e}", "error")
            continue

        # Execute ready tasks
        for rec in cypher(LEAF_Q):
            with Session(engine) as session:
                task_obj = session.get(Task, rec["id"])
            if not task_obj:
                continue
            if task_obj.purpose_id and pool.get(f"pause:{TENANT}:{task_obj.purpose_id}"):
                continue
            cost_est = (task_obj.tokens_plan or 0) * (TOKEN_PRICE_PER_1000 / 1000.0)
            budget_val = budget_left(TENANT, task_obj.purpose_id)
            if budget_val < cost_est:
                Repo(TENANT).update(task_obj.id, status="budget_exceeded", notes="budget skip")
                alert(f"Task {task_obj.id} skipped due to insufficient budget", "budget")
                continue
            role = task_obj.agent_role or classify_role(rec["d"])
            Repo(TENANT).update(task_obj.id, status="doing")
            debit(TENANT, cost_est, task_obj.purpose_id)
            celery.send_task(f"agent.{role}", args=[TENANT, rec["id"]], queue=f"{TENANT}:{role}")

        if time.time() - last > 10:
            blocked = cypher(BLOCKED_Q)[0]["blocked"]
            crit = cypher(CRIT_Q)
            PROM_TASK_BLOCKED.labels(TENANT).set(blocked)
            if crit:
                PROM_CRIT_PATH_LEN.labels(TENANT).set(crit[0]["l"])
            BUDGET_GA.labels(TENANT).set(budget_left(TENANT))
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

        await asyncio.sleep(2)


if __name__ == "__main__":
    import os
    import sys

    if not (
        os.path.isdir(os.path.join(os.getcwd(), "alembic"))
        or os.path.isdir(os.path.join(os.path.dirname(__file__), os.pardir, "alembic"))
    ):
        print("Alembic folder missing – please run 'alembic init alembic' to create it.")
        sys.exit(1)

    from ai_org_backend.services.llm_client import ensure_client

    key_present = any(
        os.getenv(v)
        for v in [
            "OPENAI_API_KEY",
            "OPENAI_KEY",
            "OPENAI_APIKEY",
            "OPENAI_API_KEY_FILE",
            "OPENAI_API_KEY_B64",
        ]
    )
    if key_present:
        try:
            ensure_client()
        except Exception as e:
            print(f"⚠️ [ORCH] OpenAI client init failed (continuing without LLM): {e}")
    else:
        print("⚠️ [ORCH] No OPENAI_API_KEY found; skipping LLM features.")

    from ai_org_backend.orchestrator.graph_orchestrator import driver

    try:
        with driver.session() as session:
            session.run("CREATE INDEX IF NOT EXISTS FOR (t:Task) ON (t.status)")
            print("ℹ️ Ensured Neo4j index on Task(status) exists")
    except Exception as e:
        logging.error("Failed to create Neo4j index for Task(status): %s", e)

    asyncio.run(orchestrator())
