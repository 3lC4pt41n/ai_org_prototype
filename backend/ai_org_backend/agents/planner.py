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
from ai_org_backend.models import Artifact, Task, TaskDependency
from ai_org_backend.models.chat import ChatRole
from ai_org_backend.orchestrator.inspector import alert
from ai_org_backend.orchestrator.role_rules import heuristic_role
from ai_org_backend.redis_client import pool
from ai_org_backend.scripts.seed_graph import ingest
from ai_org_backend.services.storage import resolve_for_read
from ai_org_backend.tasks.celery_app import celery
from ai_org_backend.utils.llm import chat

from .utils import load_template

PLANNER_RUNS = prom_counter("ai_planner_runs_total", "Planner executions")
PLANNER_LATENCY = prom_hist("ai_planner_latency_seconds", "Planner latency")
PROMPT_TMPL = load_template("planner.j2")

# Maximum allowed retries for invalid LLM output (total 3 attempts)
MAX_AGENT_RETRIES = 2

# Expected schema for a task list
TASKS_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "description": {"type": "string"},
            "depends_on": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "business_value": {"type": "number"},
            "tokens_plan": {"type": "integer"},
            "purpose_relevance": {"type": "number"},
        },
        "required": [
            "id",
            "description",
            "depends_on",
            "business_value",
            "tokens_plan",
            "purpose_relevance",
        ],
    },
}

# Regex to extract JSON from Markdown code blocks
MD_JSON_RX = re.compile(r"```json([\s\S]+?)```", re.IGNORECASE)


def run_planner(blueprint: str, tenant_id: str | None = None) -> list[dict]:
    """Generate a structured task plan (list of tasks with dependencies) from the blueprint."""
    ctx = {"task": blueprint}
    prompt = PROMPT_TMPL.render(**ctx)
    tasks: list[dict] = []
    model = "o3"
    for attempt in range(MAX_AGENT_RETRIES + 1):
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
            tasks = tasks_data
            break

        # No valid result -> prepare next attempt
        if attempt < MAX_AGENT_RETRIES:
            note_msg = (
                "previous output was not valid JSON"
                if data is None
                else "previous output did not follow the expected JSON format"
            )
            ctx["error_note"] = note_msg
            prompt = PROMPT_TMPL.render(**ctx)
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
def planner_task(tenant_id: str, purpose_id: str) -> None:
    """Celery task for Planner Agent: generates development tasks once blueprint and review are completed."""

    plan_key = f"plan_pending:{tenant_id}:{purpose_id}"
    try:
        blueprint_md = ""

        # Fetch the latest architecture blueprint artifact content
        with Session(engine) as session:
            blueprint_task = session.exec(
                select(Task).where(
                    Task.purpose_id == purpose_id,
                    func.lower(Task.description) == "architecture blueprint",
                )
            ).first()
            blueprint_artifact = None
            if blueprint_task:
                blueprint_artifact = session.exec(
                    select(Artifact)
                    .where(Artifact.task_id == blueprint_task.id)
                    .order_by(desc(Artifact.created_at))
                ).first()

        if blueprint_artifact:
            try:
                blueprint_path = resolve_for_read(blueprint_artifact.repo_path)
                blueprint_md = blueprint_path.read_text(encoding="utf-8", errors="ignore")
            except Exception as e:  # pragma: no cover - best effort logging
                alert(
                    f"Planner: Failed to read blueprint artifact for purpose {purpose_id}: {e}",
                    "warn",
                )
                logging.error(
                    "[Planner] Failed to read blueprint artifact for purpose %s: %s",
                    purpose_id,
                    e,
                )
                blueprint_md = ""
        else:
            logging.warning("[Planner] No blueprint artifact found for purpose %s", purpose_id)

        # Run LLM-based planner to generate task plan
        try:
            tasks_plan = run_planner(blueprint_md, tenant_id=tenant_id)
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

        # Remove any blueprint/review or code review/refactor tasks from initial plan
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
            if role in ("qa_review", "qa_refactor"):
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
                    owner="Review",
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
