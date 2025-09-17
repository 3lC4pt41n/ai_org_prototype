from __future__ import annotations

import asyncio
import logging
import time

from sqlalchemy import desc, not_
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
    from ai_org_backend.agents.planner import run_planner
    from ai_org_backend.scripts.seed_graph import ingest
    from ai_org_backend.services.storage import resolve_for_read, save_artefact

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

    # Decide whether to run Architect or Planner
    if blueprint_task and blueprint_task.status == TaskStatus.DONE:
        if review_task and review_task.status == TaskStatus.DONE:
            # Run Planner to generate follow-up tasks
            blueprint_md = ""
            with Session(engine) as db_session:
                blueprint_artifact = db_session.exec(
                    select(Artifact)
                    .where(Artifact.task_id == blueprint_task.id)
                    .order_by(desc(Artifact.created_at))
                ).first()
            if blueprint_artifact:
                try:
                    blueprint_path = resolve_for_read(blueprint_artifact.repo_path)
                    blueprint_md = blueprint_path.read_text(encoding="utf-8", errors="ignore")
                except Exception as e:
                    alert(
                        f"Orchestrator: Failed to read blueprint artifact for purpose {purpose_id}: {e}",
                        "warn",
                    )
                    blueprint_md = ""
            else:
                logging.warning(
                    "[Orchestrator] No blueprint artifact found for purpose %s",
                    purpose_id,
                )
            try:
                tasks_plan = run_planner(blueprint_md, tenant_id=tenant_id)
            except Exception as e:
                alert(f"Orchestrator: Planner failed for purpose {purpose_id}: {e}", "error")
                return
            if not isinstance(tasks_plan, list):
                alert("Planner returned no task list", "warn")
                return
            if not tasks_plan:
                alert("Planner returned no task list", "warn")
                return

            # Ensure a repository initialization task exists
            if not any(
                str(t.get("description", "")).lower().startswith("initialize repository")
                for t in tasks_plan
            ):
                tasks_plan.insert(
                    0,
                    {
                        "id": "repo_init",
                        "description": "Initialize repository scaffolding",
                        "business_value": 1.0,
                        "tokens_plan": 0,
                        "purpose_relevance": 0.0,
                    },
                )

            # Save generated tasks to DB
            id_map: dict[str, str] = {}
            with Session(engine) as db_session:
                for t in tasks_plan:
                    task_obj = Task(
                        tenant_id=tenant_id,
                        purpose_id=purpose_id,
                        description=t.get("description", ""),
                        business_value=float(t.get("business_value", 1.0)),
                        tokens_plan=int(t.get("tokens_plan", 0)),
                        purpose_relevance=float(t.get("purpose_relevance", 0.0)),
                        status="todo",
                    )
                    db_session.add(task_obj)
                    db_session.flush()
                    db_session.refresh(task_obj)
                    plan_id = t.get("id")
                    if plan_id is not None:
                        id_map[str(plan_id)] = task_obj.id
                db_session.commit()

            # Wire dependencies: plan-defined and review gating
            with Session(engine) as db_session:
                review_task_db = db_session.exec(
                    select(Task).where(
                        Task.purpose_id == purpose_id,
                        func.lower(Task.description) == "architecture & domain review",
                    )
                ).first()
                if not review_task_db:
                    # Fallback: create review task if missing (should not happen here)
                    review_task_db = Task(
                        tenant_id=tenant_id,
                        purpose_id=purpose_id,
                        description="Architecture & Domain Review",
                        business_value=0.0,
                        tokens_plan=0,
                        purpose_relevance=1.0,
                        status="todo",
                        owner="Review",
                        notes="awaiting_approval",
                    )
                    db_session.add(review_task_db)
                    db_session.commit()
                    db_session.refresh(review_task_db)
                # Task plan internal dependencies
                for t in tasks_plan:
                    plan_id = t.get("id")
                    if plan_id is None:
                        continue
                    plan_id_str = str(plan_id)
                    dep = t.get("depends_on")
                    dep_str = str(dep) if dep is not None else None
                    if (
                        dep_str
                        and dep_str in id_map
                        and plan_id_str in id_map
                        and id_map[dep_str] != id_map[plan_id_str]
                    ):
                        db_session.add(
                            TaskDependency(
                                from_id=id_map[dep_str],
                                to_id=id_map[plan_id_str],
                                dependency_type="FINISH_START",
                            )
                        )
                # Ensure all new tasks depend on the review task
                for tid in id_map.values():
                    exists = db_session.exec(
                        select(TaskDependency).where(
                            TaskDependency.from_id == review_task_db.id,
                            TaskDependency.to_id == tid,
                        )
                    ).first()
                    if not exists:
                        db_session.add(
                            TaskDependency(
                                from_id=review_task_db.id,
                                to_id=tid,
                                dependency_type="FINISH_START",
                            )
                        )
                db_session.commit()
            try:
                ingest(tenant_id)
            except Exception as e:
                alert(f"Orchestrator: ingest failed for purpose {purpose_id}: {e}", "warn")
            return
        else:
            # Review not yet approved; wait before planning
            return

    # Run Architect to generate architecture blueprint and initial tasks
    try:
        blueprint_md = run_architect(purpose)
    except Exception as e:
        alert(f"Orchestrator: Architect failed for purpose {purpose_id}: {e}", "error")
        return
    blueprint_task_id = ""
    with Session(engine) as db_session:
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
        save_artefact(
            blueprint_task_id,
            blueprint_md.encode("utf-8"),
            filename="blueprints/architecture_blueprint.md",
            media_type="text/markdown",
            allow_overwrite=True,
        )
        Repo(tenant_id).update(blueprint_task_id, owner="Architect", notes="Blueprint completed")

    with Session(engine) as db_session:
        review_task = db_session.exec(
            select(Task).where(
                Task.purpose_id == purpose_id,
                func.lower(Task.description) == "architecture & domain review",
            )
        ).first()
        if not review_task:
            review_task = Task(
                tenant_id=tenant_id,
                purpose_id=purpose_id,
                description="Architecture & Domain Review",
                business_value=0.0,
                tokens_plan=0,
                purpose_relevance=1.0,
                status="todo",
                owner="Review",
                notes="awaiting_approval",
            )
            db_session.add(review_task)
            db_session.commit()
            db_session.refresh(review_task)
        edge_exists = db_session.exec(
            select(TaskDependency).where(
                TaskDependency.from_id == blueprint_task_id,
                TaskDependency.to_id == review_task.id,
            )
        ).first()
        if not edge_exists:
            db_session.add(
                TaskDependency(
                    from_id=blueprint_task_id,
                    to_id=review_task.id,
                    dependency_type="FINISH_START",
                )
            )
        tasks = db_session.exec(select(Task).where(Task.purpose_id == purpose_id)).all()
        for t in tasks:
            desc_val = (t.description or "").strip().lower()
            if t.id in (blueprint_task_id, review_task.id) or desc_val in [
                "product requirements document",
                "architecture blueprint",
                "architecture & domain review",
            ]:
                continue
            exists = db_session.exec(
                select(TaskDependency).where(
                    TaskDependency.from_id == review_task.id,
                    TaskDependency.to_id == t.id,
                )
            ).first()
            if not exists:
                db_session.add(
                    TaskDependency(
                        from_id=review_task.id,
                        to_id=t.id,
                        dependency_type="FINISH_START",
                    )
                )
        db_session.commit()

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
        purpose_to_process: tuple[Purpose, bool] | None = None
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
                    if prd_task and (prd_art and prd_art.released) and not blueprint_task:
                        purpose_to_process = (p, bool(impl_todo))
                        break
        except Exception as e:
            logging.error("[Orchestrator] Failed to poll purposes: %s", e)

        if purpose_to_process:
            p, has_impl_todo = purpose_to_process
            logging.info(
                "[Orchestrator] Approved PRD for purpose %s -> start Architect (impl_todo=%s)",
                p.id,
                has_impl_todo,
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
            role = classify_role(rec["d"])
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
