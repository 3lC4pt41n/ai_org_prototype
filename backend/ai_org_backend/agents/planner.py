from __future__ import annotations

import json
import logging
import re
import time

from jsonschema import validate
from sqlalchemy import desc, func
from sqlmodel import Session, select

from ai_org_backend.db import engine
from ai_org_backend.metrics import prom_counter, prom_hist
from ai_org_backend.models import Artifact, Task, TaskDependency, TaskOwner
from ai_org_backend.models.chat import ChatRole
from ai_org_backend.orchestrator.inspector import alert
from ai_org_backend.orchestrator.role_rules import heuristic_role
from ai_org_backend.redis_client import pool
from ai_org_backend.scripts.seed_graph import ingest
from ai_org_backend.services.artifact_resolver import load_by_phase
from ai_org_backend.services.cumulative_context import load_cumulative_context
from ai_org_backend.services.cycle_detector import validate_no_cycles, validate_refs, CyclicDependencyError
from ai_org_backend.services.feedback_loop import load_feedback_context
from ai_org_backend.services.storage import resolve_for_read
from ai_org_backend.tasks.celery_app import celery
from ai_org_backend.utils.llm import chat

from .utils import load_template

PLANNER_RUNS = prom_counter("ai_planner_runs_total", "Planner executions")


def _fail_task(task_id: str, tenant_id: str, reason: str) -> None:
    """S-Sprint1 Fix #9: Mark a task as failed with a descriptive reason."""
    from ai_org_backend.services.repo import Repo

    try:
        Repo(tenant_id).update(task_id, status="failed", notes=reason)
    except Exception as exc:
        logging.error("[Planner] Failed to mark task %s as failed: %s", task_id, exc)
PLANNER_LATENCY = prom_hist("ai_planner_latency_seconds", "Planner latency")
PROMPT_TMPL = load_template("planner.j2")

# Maximum allowed retries for invalid LLM output (total 3 attempts)
MAX_AGENT_RETRIES = 2

CODE_FILE_SUFFIXES = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".java",
    ".go",
    ".rb",
    ".rs",
    ".php",
    ".swift",
    ".cs",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
}

QA_DELAYED_DESCRIPTIONS = {
    "code review",
    "refactor codebase",
}


def _looks_like_code_artifact(artifact: Artifact) -> bool:
    repo_path = (artifact.repo_path or "").lower()
    media_type = (artifact.media_type or "").lower()
    if media_type.startswith("text/x-"):
        return True
    return any(repo_path.endswith(suffix) for suffix in CODE_FILE_SUFFIXES)


# S3-05: Enhanced schema for a task list with bounds and refs
TASKS_SCHEMA = {
    "type": "array",
    "minItems": 1,
    "maxItems": 200,
    "items": {
        "type": "object",
        "properties": {
            "id": {"type": "string", "minLength": 1, "maxLength": 50},
            "description": {"type": "string", "minLength": 3, "maxLength": 2000},
            "depends_on": {"anyOf": [
                {"type": "string", "minLength": 1, "maxLength": 50},
                {"type": "null"},
            ]},
            "business_value": {"type": "number", "minimum": 0.0, "maximum": 10.0},
            "tokens_plan": {"type": "integer", "minimum": 0, "maximum": 1_000_000},
            "purpose_relevance": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            # S3-05: Optional extended fields for richer planning
            "agent_role": {"anyOf": [
                {"type": "string", "minLength": 1, "maxLength": 50},
                {"type": "null"},
            ]},
            "model_name": {"anyOf": [
                {"type": "string", "maxLength": 100},
                {"type": "null"},
            ]},
        },
        "required": [
            "id",
            "description",
            "depends_on",
            "business_value",
            "tokens_plan",
            "purpose_relevance",
        ],
        # S-Sprint4 Fix #25: Reject unexpected fields from LLM output
        "additionalProperties": False,
    },
}

# Regex to extract JSON from Markdown code blocks
MD_JSON_RX = re.compile(r"```json([\s\S]+?)```", re.IGNORECASE)


def run_planner(
    blueprint: str, tenant_id: str | None = None, purpose_id: str | None = None
) -> list[dict]:
    """Generate a structured task plan (list of tasks with dependencies) from the blueprint."""
    ctx = {"task": blueprint}
    prompt_template = PROMPT_TMPL
    template_key: str | None = None
    if purpose_id:
        try:
            with Session(engine) as session:
                plan_task = session.exec(
                    select(Task)
                    .where(Task.purpose_id == purpose_id)
                    .where(func.lower(Task.description) == "implementation plan")
                ).first()
                if plan_task and plan_task.prompt_template:
                    template_key = plan_task.prompt_template
        except Exception:
            logging.exception(
                "[Planner] Failed to resolve custom prompt for purpose %s", purpose_id
            )
    if template_key:
        try:
            prompt_template = load_template(template_key)
        except FileNotFoundError:
            logging.warning(
                "[Planner] Prompt %s not found; using default", template_key
            )
        except Exception:
            logging.exception("[Planner] Failed to load prompt %s", template_key)

    prompt = prompt_template.render(**ctx)
    tasks: list[dict] = []
    model = "o3"
    for attempt in range(MAX_AGENT_RETRIES + 1):
        logging.info(
            "[Planner] Generating plan (attempt %d) for tenant=%s",
            attempt + 1,
            tenant_id,
        )
        start = time.time()
        try:
            resp = chat(
                model=model,
                messages=[{"role": ChatRole.USER.value, "content": prompt}],
                tenant_id=tenant_id,
            )
            PLANNER_RUNS.inc()
        finally:
            PLANNER_LATENCY.observe(time.time() - start)
        plan_text = resp.choices[0].message.content
        logging.debug("[Planner] Raw plan text:\n%s", plan_text[:500])

        data = None
        try:
            # 1) Direktes JSON-Parsing
            data = json.loads(plan_text)
        except json.JSONDecodeError:
            # 2) Fallback: JSON aus Markdown-Codeblock extrahieren
            m = MD_JSON_RX.search(plan_text)
            if m:
                try:
                    data = json.loads(m.group(1))
                except Exception:
                    data = None
            # 3) Weiterer Fallback: zwischen erstem '[' und letztem ']'
            if data is None:
                try:
                    lo = plan_text.index("[")
                    hi = plan_text.rindex("]")
                    snippet = plan_text[lo : hi + 1]
                    data = json.loads(snippet)
                except Exception:
                    data = None

        tasks_data = None
        if data:
            if isinstance(data, dict) and "tasks" in data:
                tasks_data = data["tasks"]
            elif isinstance(data, list):
                tasks_data = data
            # Schema validieren
            try:
                if tasks_data is not None:
                    validate(instance=tasks_data, schema=TASKS_SCHEMA)
                else:
                    raise ValueError("Schema validation skipped due to missing tasks list")
            except Exception:
                tasks_data = None

        if tasks_data:
            # S3-06: Validate dependency graph for cycles
            try:
                validate_no_cycles(tasks_data)
            except CyclicDependencyError as exc:
                logging.warning(
                    "[Planner] Cycle detected in LLM output (attempt %d): %s",
                    attempt + 1, exc,
                )
                tasks_data = None
            # S3-05: Warn about dangling refs but don't reject
            if tasks_data:
                ref_warnings = validate_refs(tasks_data)
                for w in ref_warnings:
                    logging.warning("[Planner] Dangling ref: %s", w)

        if tasks_data:
            tasks = tasks_data
            break

        # No valid result -> prepare next attempt
        if attempt < MAX_AGENT_RETRIES:
            note_msg = (
                "previous output was not valid JSON"
                if data is None
                else "previous output did not follow the expected JSON format"
            )
            # S-Sprint4 Fix #25: Include full schema in error_note so LLM
            # knows the exact expected format on retry
            schema_hint = json.dumps(TASKS_SCHEMA, indent=2)
            ctx["error_note"] = (
                f"{note_msg}. You MUST return a JSON array matching this schema "
                f"exactly (no extra fields allowed):\n{schema_hint}"
            )
            prompt = PROMPT_TMPL.render(**ctx)
            # S-Sprint4 Fix #25: Lower temperature on retry for deterministic output
            model = "o3-pro"
            logging.warning(
                "[Planner] invalid LLM output (attempt %s/%s): %s",
                attempt + 1,
                MAX_AGENT_RETRIES + 1,
                note_msg,
            )
        else:
            logging.error(f"[Planner] no valid task list after {attempt + 1} attempts")

    return tasks


@celery.task(name="agent.planner")
def planner_task(
    tenant_id: str,
    task_id: str | None = None,
    purpose_id: str | None = None,
) -> None:
    """Celery task for Planner Agent: generates development tasks once blueprint and review are completed."""

    if purpose_id is None and task_id:
        with Session(engine) as session:
            task_obj = session.get(Task, task_id)
            if task_obj and task_obj.purpose_id:
                purpose_id = task_obj.purpose_id

    if purpose_id is None:
        alert(
            f"Planner: Unable to resolve purpose for task {task_id}",
            "error",
        )
        logging.error(
            "[Planner] Cannot determine purpose for planner task (task_id=%s)",
            task_id,
        )
        return

    plan_key = f"plan_pending:{tenant_id}:{purpose_id}"
    try:
        blueprint_md = ""
        code_artifact_exists = False

        # S3-04/S3-09: Use artifact resolver + cumulative context
        # S-Sprint1 Fix #9: require_artifact=True → fail explicitly if missing
        from ai_org_backend.services.artifact_resolver import ArtifactNotFoundError
        try:
            blueprint_md = load_by_phase(
                purpose_id, "architecture blueprint", require_artifact=True
            ) or ""
        except ArtifactNotFoundError as exc:
            logging.error("[Planner][S1-#9] %s", exc)
            _fail_task(task_id, tenant_id, str(exc))
            return
        if not blueprint_md:
            logging.warning("[Planner] No blueprint artifact found for purpose %s", purpose_id)

        # S3-09: Load cumulative context (PRD + Architecture) for richer planning
        cumctx = load_cumulative_context(
            purpose_id, up_to="architecture & domain review"
        )

        with Session(engine) as session:
            code_artifact_exists = any(
                _looks_like_code_artifact(artifact)
                for artifact in session.exec(
                    select(Artifact)
                    .join(Task, Task.id == Artifact.task_id)
                    .where(Task.purpose_id == purpose_id)
                )
            )

        # S4-11: Load feedback context for planner
        feedback_ctx = ""
        try:
            feedback_ctx = load_feedback_context("", purpose_id=purpose_id)
        except Exception:
            pass
        if feedback_ctx:
            blueprint_md = f"{blueprint_md}\n\n{feedback_ctx}"

        # Run LLM-based planner to generate task plan
        try:
            tasks_plan = run_planner(
                blueprint_md, tenant_id=tenant_id, purpose_id=purpose_id
            )
        except Exception as e:  # pragma: no cover - LLM/runtime failure
            msg = f"Planner agent failed for purpose {purpose_id}: {e}"
            alert(msg, "error")
            logging.error("[Planner] %s", msg)
            return

        if not isinstance(tasks_plan, list):
            msg = f"Planner returned invalid result for purpose {purpose_id}"
            alert(msg, "warn")
            logging.warning("[Planner] %s", msg)
            return

        # Remove any blueprint/review or premature QA tasks from the initial plan
        filtered_plan: list[dict] = []
        for t in tasks_plan:
            desc_text = str(t.get("description", "")).strip().lower()
            if desc_text in [
                "architecture blueprint",
                "architecture & domain review",
                "product requirements document",
            ]:
                continue
            role = heuristic_role(t.get("description", ""))
            if (not code_artifact_exists) and (
                role in ("qa_review", "qa_refactor")
                or desc_text in QA_DELAYED_DESCRIPTIONS
            ):
                logging.debug(
                    "[Planner] Skip early QA task '%s' until code artifacts exist",
                    t.get("description", ""),
                )
                continue
            filtered_plan.append(t)

        tasks_plan = filtered_plan

        if not tasks_plan:
            msg = f"Planner returned empty task list for purpose {purpose_id}"
            alert(msg, "warn")
            logging.warning("[Planner] %s", msg)
            return

        # Ensure repository initialization task is first in plan
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

        # Save generated tasks to database and map their IDs
        id_map: dict[str, str] = {}
        with Session(engine) as session:
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
                session.add(task_obj)
                session.flush()
                session.refresh(task_obj)
                plan_id = t.get("id")
                if plan_id is not None:
                    id_map[str(plan_id)] = task_obj.id
            session.commit()

        # Create task dependencies (LLM-defined and review gating)
        with Session(engine) as session:
            review_task = session.exec(
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
                    owner=TaskOwner.REVIEW,
                    notes="awaiting_approval",
                )
                session.add(review_task)
                session.commit()
                session.refresh(review_task)

            for t in tasks_plan:
                dep = t.get("depends_on")
                if dep:
                    dep_str = str(dep)
                    plan_id_str = str(t.get("id"))
                    if (
                        dep_str in id_map
                        and plan_id_str in id_map
                        and id_map[dep_str] != id_map[plan_id_str]
                    ):
                        session.add(
                            TaskDependency(
                                from_id=id_map[dep_str],
                                to_id=id_map[plan_id_str],
                                dependency_type="FINISH_START",
                            )
                        )

            for new_tid in id_map.values():
                exists = session.exec(
                    select(TaskDependency).where(
                        TaskDependency.from_id == review_task.id,
                        TaskDependency.to_id == new_tid,
                    )
                ).first()
                if not exists:
                    session.add(
                        TaskDependency(
                            from_id=review_task.id,
                            to_id=new_tid,
                            dependency_type="FINISH_START",
                        )
                    )

            session.commit()

        # Update the knowledge graph with new tasks
        try:
            ingest(tenant_id)
        except Exception as e:  # pragma: no cover - best effort logging
            alert(f"Planner: ingest failed for purpose {purpose_id}: {e}", "warn")
            logging.error("[Planner] Ingest failed for purpose %s: %s", purpose_id, e)
    finally:
        try:
            pool.delete(plan_key)
        except Exception as exc:  # pragma: no cover - best effort logging
            logging.warning(
                "[Planner] Failed to clear pending flag for purpose %s: %s",
                purpose_id,
                exc,
            )
