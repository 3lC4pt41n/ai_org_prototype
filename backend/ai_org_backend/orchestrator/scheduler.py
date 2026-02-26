from __future__ import annotations

import asyncio
import logging
import re
import time

from typing import Optional

from sqlmodel import Session, func, select

from ai_org_backend.db import engine
from ai_org_backend.metrics import BUDGET_GA
from ai_org_backend.redis_client import pool
from ai_org_backend.services.repo import Repo, budget_left, debit
from ai_org_backend.settings import settings
from ai_org_backend.tasks.celery_app import celery

# Aliases für lange Task-Beschreibungen → Phase-Slugs
PHASE_ALIAS = {
    "product requirements document": "prd",
    "architecture blueprint": "architecture",
    "architecture & domain review": "architecture_review",
}

TOKEN_PRICE_PER_1000 = settings.token_price_per_1000
from ai_org_backend.models import (
    Artifact,
    PipelinePhase,
    Purpose,
    Task,
    TaskDependency,
    TaskOwner,
    TaskStatus,
)
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


def _resolve_agent_role(
    session: Session, task: Task, role_hint: str | None = None
) -> str | None:
    """Resolve the agent role for a task."""

    # 1. Wenn direkt gesetzt → nutzen
    if task.agent_role:
        return task.agent_role

    # 2. Phase über pipeline_phase_id oder slug
    phase: PipelinePhase | None = None
    if task.pipeline_phase_id:
        phase = session.get(PipelinePhase, task.pipeline_phase_id)

    if phase is None and task.description:
        slug = (task.description or "").lower().strip()
        slug = PHASE_ALIAS.get(slug, slug)
        phase = session.exec(
            select(PipelinePhase).where(PipelinePhase.slug == slug)
        ).first()

    if phase and phase.agent_role:
        return phase.agent_role

    # 3. Fallback auf Heuristik
    return role_hint


def _slugify_phase_name(value: str) -> str:
    value = value.lower().replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "phase"


def _resolve_pipeline_phase(session: Session, task: Task) -> Optional[PipelinePhase]:
    if task.pipeline_phase_id:
        return session.get(PipelinePhase, task.pipeline_phase_id)

    slug = getattr(task, "slug", None)
    if not slug and task.description:
        raw = (task.description or "").strip().lower()
        slug = PHASE_ALIAS.get(raw)
        if not slug:
            slug = _slugify_phase_name(raw)

    if not slug:
        return None

    return session.exec(select(PipelinePhase).where(PipelinePhase.slug == slug)).first()


def _dispatch_task(
    session: Session,
    task: Task,
    tenant_id: str,
    *,
    role: str | None = None,
    cost_estimate: float = 0.0,
) -> Optional[bool]:
    """Dispatch pipeline phase tasks respecting predecessor completion order.

    Returns ``True`` if the task was dispatched, ``False`` if dispatch is blocked
    because a predecessor phase is not yet complete, and ``None`` if the task is
    not associated with a pipeline phase.
    """

    phase = _resolve_pipeline_phase(session, task)
    if phase is None:
        return None

    predecessor_phase: Optional[PipelinePhase] = None
    depends_on_slug = getattr(phase, "depends_on", None)
    if depends_on_slug:
        predecessor_phase = session.exec(
            select(PipelinePhase).where(PipelinePhase.slug == depends_on_slug)
        ).first()
    elif phase.predecessor_id:
        predecessor_phase = session.get(PipelinePhase, phase.predecessor_id)

    if predecessor_phase:
        predecessor_task = session.exec(
            select(Task)
            .where(Task.purpose_id == task.purpose_id)
            .where(Task.pipeline_phase_id == predecessor_phase.id)
            .where(Task.status == TaskStatus.DONE)
        ).first()
        if not predecessor_task:
            predecessor_label = (
                getattr(predecessor_phase, "slug", None)
                or depends_on_slug
                or predecessor_phase.id
                if predecessor_phase
                else "unknown"
            )
            logging.info(
                "[Orchestrator] Skip %s, predecessor %s not done yet",
                getattr(phase, "slug", task.description or task.id),
                predecessor_label,
            )
            return False

    phase_slug = (getattr(phase, "slug", None) or "").lower()
    purpose = session.get(Purpose, task.purpose_id) if task.purpose_id else None
    if purpose and purpose.mode == "manual":
        approval_dependencies: dict[str, str] = {
            "prd": "vision document",
            "architecture": "product requirements document",
            "architecture_review": "architecture blueprint",
            "implementation": "architecture & domain review",
        }
        required_desc = approval_dependencies.get(phase_slug)
        if required_desc:
            required_task = session.exec(
                select(Task).where(
                    Task.purpose_id == task.purpose_id,
                    func.lower(Task.description) == required_desc,
                )
            ).first()
            required_artifact = (
                session.exec(
                    select(Artifact)
                    .where(Artifact.task_id == required_task.id)
                    .order_by(Artifact.created_at.desc())
                ).first()
                if required_task
                else None
            )
            if not required_artifact or not required_artifact.released:
                logging.info(
                    "[Orchestrator] Skip %s, waiting for approval of %s in purpose %s",
                    phase_slug or task.description or task.id,
                    required_desc,
                    task.purpose_id,
                )
                return False

    resolved_role = role or task.agent_role or getattr(phase, "agent_role", None)
    if not resolved_role:
        logging.warning(
            "[Orchestrator] No agent role resolved for pipeline task %s (tenant %s)",
            task.id,
            tenant_id,
        )
        return False

    Repo(tenant_id).update(
        task.id,
        status="doing",
        owner=resolved_role.capitalize(),
    )

    if cost_estimate > 0:
        debit(tenant_id, cost_estimate, task.purpose_id)

    celery.send_task(
        f"agent.{resolved_role}",
        args=[tenant_id, task.id, task.purpose_id],
        queue=f"{tenant_id}:{resolved_role}",
    )
    logging.info(
        "[Orchestrator] Dispatched %s to %s",
        getattr(phase, "slug", task.description or task.id),
        resolved_role,
    )
    return True


def _generate_plan_for_purpose(purpose_id: str) -> None:
    from ai_org_backend.agents.architect import run_architect
    from ai_org_backend.scripts.seed_graph import ingest
    from ai_org_backend.services.storage import register_artefact

    with Session(engine) as db_session:
        purpose = db_session.get(Purpose, purpose_id)
        if not purpose:
            alert(f"Purpose {purpose_id} not found for planning", "orchestrator")
            return
        tenant_id = purpose.tenant_id
        purpose_mode = purpose.mode
        vision_task = db_session.exec(
            select(Task).where(
                Task.purpose_id == purpose_id,
                func.lower(Task.description) == "vision document",
            )
        ).first()
        po_task = db_session.exec(
            select(Task).where(
                Task.purpose_id == purpose_id,
                func.lower(Task.description) == "product requirements document",
            )
        ).first()
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

        def _latest_artifact_for(task_obj: Task | None) -> Artifact | None:
            if not task_obj:
                return None
            return db_session.exec(
                select(Artifact)
                .where(Artifact.task_id == task_obj.id)
                .order_by(Artifact.created_at.desc())
            ).first()

        vision_artifact = _latest_artifact_for(vision_task)
        prd_artifact = _latest_artifact_for(po_task)
        blueprint_artifact = _latest_artifact_for(blueprint_task)
        review_artifact = _latest_artifact_for(review_task)

        if vision_task and vision_task.status == TaskStatus.DONE and not po_task:
            vision_approved = bool(
                purpose_mode == "auto"
                or (vision_artifact and vision_artifact.released)
                or "approved" in (vision_task.notes or "").lower()
            )
            if vision_approved:
                new_task = Task(
                    tenant_id=tenant_id,
                    purpose_id=purpose_id,
                    description="Product Requirements Document",
                    status="todo",
                    owner="PO",
                    agent_role="po",
                    notes="awaiting_completion",
                )
                db_session.add(new_task)
                db_session.commit()
                db_session.refresh(new_task)
                logging.info(
                    "[Orchestrator] Created PRD Task %s for purpose %s",
                    new_task.id,
                    purpose_id,
                )
            else:
                logging.info(
                    "[Orchestrator] Vision completed but not approved yet for purpose %s",
                    purpose_id,
                )
            return

        prd_ready_for_architecture = bool(
            po_task
            and po_task.status == TaskStatus.DONE
            and prd_artifact
            and (purpose_mode == "auto" or prd_artifact.released)
        )
        if not prd_ready_for_architecture and not blueprint_task:
            logging.debug(
                "[Orchestrator] Waiting for approved PRD before architecture for purpose %s",
                purpose_id,
            )
            return

        if (
            blueprint_task
            and blueprint_task.status == TaskStatus.DONE
            and review_task is None
        ):
            if purpose_mode == "manual" and not (
                blueprint_artifact and blueprint_artifact.released
            ):
                logging.info(
                    "[Orchestrator] Blueprint exists but not approved yet for purpose %s",
                    purpose_id,
                )
                return
            review_phase = db_session.exec(
                select(PipelinePhase).where(PipelinePhase.slug == "architecture_review")
            ).first()
            repo = Repo(tenant_id)
            review_task_obj = repo.add_task(
                purpose_id=purpose_id,
                description="Architecture & Domain Review",
                business_value=getattr(review_phase, "business_value_default", 1.0),
                tokens_plan=getattr(review_phase, "tokens_plan_default", 1500),
                purpose_relevance=getattr(review_phase, "purpose_relevance_default", 1.0),
                pipeline_phase_id=getattr(review_phase, "id", None),
                agent_role=getattr(review_phase, "agent_role", "reviewer"),
                model_name=getattr(review_phase, "model_name", None),
                prompt_template=getattr(review_phase, "prompt_template", None),
                requires_approval=getattr(review_phase, "requires_approval", True),
            )
            repo.link(blueprint_task.id, review_task_obj.id)
            repo.update(
                review_task_obj.id,
                status="doing",
                owner=TaskOwner.REVIEW,
                notes="Review in progress",
            )
            logging.info(
                "[Orchestrator] Created Architecture Review task %s for purpose %s – dispatching reviewer",
                review_task_obj.id,
                purpose_id,
            )
            # Dispatch the reviewer agent immediately so the task is actually executed
            celery.send_task(
                "agent.reviewer",
                args=[tenant_id, review_task_obj.id, purpose_id, blueprint_task.id],
                queue=f"{tenant_id}:reviewer",
            )
            return

        # Decide whether to run Planner (nur wenn Review freigegeben ist)
        # Note: must stay inside the `with Session` block so blueprint_task/review_task
        # are still attached to the session.
        if (
            blueprint_task
            and blueprint_task.status == TaskStatus.DONE
            and review_task
            and review_task.status == TaskStatus.DONE
        ):
            if purpose_mode == "manual" and not (
                review_artifact and review_artifact.released
            ):
                logging.info(
                    "[Orchestrator] Review exists but not approved yet for purpose %s",
                    purpose_id,
                )
                return
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
                    args=[tenant_id, None, purpose_id],
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
        register_artefact(
            blueprint_task_id,
            blueprint_md.encode("utf-8"),
            filename="blueprints/architecture_blueprint.md",
            media_type="text/markdown",
            allow_overwrite=True,
        )
        Repo(tenant_id).update(
            blueprint_task_id,
            owner=TaskOwner.ARCHITECT,
            notes="Blueprint completed",
        )

    # In manual mode: pause so the user can review the architecture blueprint
    # before the scheduler creates the review phase.
    if purpose_mode == "manual":
        try:
            pool.set(f"pause:{tenant_id}:{purpose_id}", "1")
            logging.info(
                "[Orchestrator] Paused purpose %s after architecture generation (manual mode)",
                purpose_id,
            )
        except Exception as e:
            logging.error("Failed to set pause flag after architecture: %s", e)

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
                        ),
                        None,
                    )
                    prd_task_done = (
                        prd_task if prd_task and prd_task.status == TaskStatus.DONE else None
                    )

                    vision_task = next(
                        (
                            t
                            for t in tasks
                            if t.description and t.description.lower() == "vision document"
                        ),
                        None,
                    )

                    blueprint_task = next(
                        (t for t in tasks if t.description == "Architecture Blueprint"),
                        None,
                    )

                    prd_art = None
                    if prd_task_done:
                        prd_art = session.exec(
                            select(Artifact)
                            .where(Artifact.task_id == prd_task_done.id)
                            .order_by(Artifact.created_at.desc())
                        ).first()

                    review_task = next(
                        (
                            t
                            for t in tasks
                            if t.description
                            and t.description.lower() == "architecture & domain review"
                        ),
                        None,
                    )

                    impl_todo = next(
                        (
                            t
                            for t in tasks
                            if t.status != TaskStatus.DONE
                            and t.description
                            not in [
                                "Vision Document",
                                "Product Requirements Document",
                                "Architecture Blueprint",
                                "Architecture & Domain Review",
                                "Implementation Plan",
                            ]
                        ),
                        None,
                    )

                    logging.info(
                        f"[Orchestrator]  → prd_done={bool(prd_task_done)} "
                        f"released={getattr(prd_art,'released',None)} "
                        f"blueprint={bool(blueprint_task)} review={bool(review_task)} "
                        f"impl_todo={bool(impl_todo)}"
                    )

                    if (
                        vision_task
                        and vision_task.status == TaskStatus.DONE
                        and prd_task is None
                    ):
                        vision_art = session.exec(
                            select(Artifact)
                            .where(Artifact.task_id == vision_task.id)
                            .order_by(Artifact.created_at.desc())
                        ).first()
                        vision_released = bool(vision_art and vision_art.released)
                        notes = (vision_task.notes or "").lower()
                        if p.mode == "auto" or vision_released or "approved" in notes:
                            purpose_to_process = (p, "vision")
                            break

                    if prd_task_done and prd_art and prd_art.released and not blueprint_task:
                        purpose_to_process = (p, "architect")
                        break

                    if (
                        blueprint_task
                        and blueprint_task.status == TaskStatus.DONE
                        and not review_task
                    ):
                        # In manual mode: only proceed to review if the
                        # architecture blueprint artifact has been released
                        # (approved by the user).
                        if p.mode == "manual":
                            bp_art = session.exec(
                                select(Artifact)
                                .where(Artifact.task_id == blueprint_task.id)
                                .order_by(Artifact.created_at.desc())
                            ).first()
                            if not bp_art or not bp_art.released:
                                continue
                        purpose_to_process = (p, "review")
                        break

                    if (
                        review_task
                        and review_task.status == TaskStatus.DONE
                        and impl_todo is None
                    ):
                        # In manual mode: only proceed to planner if the
                        # review artifact has been released (approved).
                        if p.mode == "manual":
                            rev_art = session.exec(
                                select(Artifact)
                                .where(Artifact.task_id == review_task.id)
                                .order_by(Artifact.created_at.desc())
                            ).first()
                            if not rev_art or not rev_art.released:
                                continue
                        purpose_to_process = (p, "planner")
                        break
        except Exception as e:
            logging.error("[Orchestrator] Failed to poll purposes: %s", e)

        if purpose_to_process:
            p, action = purpose_to_process
            if action == "vision":
                logging.info(
                    "[Orchestrator] Vision completed for purpose %s → erstelle PRD-Task",
                    p.id,
                )
            elif action == "architect":
                logging.info(
                    "[Orchestrator] PRD freigegeben für Purpose %s → starte Architecture",
                    p.id,
                )
            elif action == "review":
                logging.info(
                    "[Orchestrator] Blueprint abgeschlossen für Purpose %s → starte Review",
                    p.id,
                )
            else:  # planner
                logging.info(
                    "[Orchestrator] Blueprint & Review abgeschlossen für Purpose %s → starte Planner",
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
                if task_obj.purpose_id and pool.get(
                    f"pause:{TENANT}:{task_obj.purpose_id}"
                ):
                    continue

                tenant_id = task_obj.tenant_id or TENANT
                cost_est = (task_obj.tokens_plan or 0) * (
                    TOKEN_PRICE_PER_1000 / 1000.0
                )
                budget_val = budget_left(tenant_id, task_obj.purpose_id)
                if budget_val < cost_est:
                    Repo(tenant_id).update(
                        task_obj.id, status="budget_exceeded", notes="budget skip"
                    )
                    alert(
                        f"Task {task_obj.id} skipped due to insufficient budget",
                        "budget",
                    )
                    continue

                role_hint = classify_role(rec["d"])
                role = _resolve_agent_role(session, task_obj, role_hint)

                dispatch_result = _dispatch_task(
                    session,
                    task_obj,
                    tenant_id,
                    role=role,
                    cost_estimate=cost_est,
                )
                if dispatch_result:
                    continue
                if dispatch_result is False:
                    continue

                if not role:
                    logging.warning(
                        "[Orchestrator] No agent role resolved for task %s (tenant %s)",
                        task_obj.id,
                        tenant_id,
                    )
                    continue

                Repo(tenant_id).update(
                    task_obj.id, status="doing", owner=role.capitalize()
                )
                debit(tenant_id, cost_est, task_obj.purpose_id)
                logging.info(
                    "[Orchestrator] Dispatching %s (task_id=%s) for tenant=%s to role=%s queue=%s",
                    task_obj.description,
                    task_obj.id,
                    tenant_id,
                    role,
                    f"{tenant_id}:{role}",
                )
                celery.send_task(
                    f"agent.{role}",
                    args=[tenant_id, task_obj.id],
                    queue=f"{tenant_id}:{role}",
                )

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
