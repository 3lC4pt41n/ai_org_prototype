from __future__ import annotations

import logging
from pathlib import Path

from jinja2 import Template

from ai_org_backend.tasks.celery_app import celery
from ai_org_backend.main import Repo, TASK_CNT, TASK_LAT, budget_left, debit, TOKEN_PRICE_PER_1000
from ai_org_backend.services.storage import save_artefact
from ai_org_backend.db import SessionLocal
from ai_org_backend.models import Task, Purpose
from ai_org_backend.utils.llm import chat
from ai_org_backend.orchestrator.inspector import PROM_TASK_FAILED

# Load prompt template for UX/UI agent
_TMPL_PATH = Path(__file__).resolve().parents[3] / "prompts" / "ux_ui.j2"
PROMPT_TMPL = Template(_TMPL_PATH.read_text(encoding="utf-8"))


@celery.task(name="agent.ux_ui")
def agent_ux_ui(tid: str, task_id: str) -> None:
    """Generate a wireframe design for the task using OpenAI."""
    logging.info(f"[UXAgent] Generating UX/UI design for task {task_id} (tenant {tid})")
    with TASK_LAT.labels("ux_ui").time():
        with SessionLocal() as session:
            task_obj = session.get(Task, task_id)
            purpose_name = ""
            if task_obj:
                if task_obj.purpose_id:
                    purpose = session.get(Purpose, task_obj.purpose_id)
                    if purpose:
                        purpose_name = purpose.name
                if not purpose_name:
                    purpose_name = "demo"
            else:
                logging.error(f"Task {task_id} not found in DB")
                return
            task_data = {
                "description": task_obj.description,
                "id": task_obj.id,
                "business_value": task_obj.business_value,
                "tokens_plan": task_obj.tokens_plan,
                "tokens_actual": task_obj.tokens_actual,
            }
            budget_val = budget_left(tid)
            ctx = {
                "purpose": purpose_name,
                "task": task_data,
                "budget_left": budget_val,
            }
            # Include error note for retry attempts
            if task_obj and task_obj.retries > 0 and task_obj.notes:
                err = task_obj.notes.strip()
                if len(err) > 200:
                    err = err[:200] + "..."
                ctx["error_note"] = err
            # Retrieve semantic memory snippets for context
            try:
                from ai_org_backend.services import memory
            except ImportError:
                memory_snippets = []
            else:
                memory_snippets = memory.get_relevant_snippets(
                    tid, task_obj.purpose_id, task_obj.description, top_k=3
                )
            ctx["memory_snippets"] = memory_snippets
        prompt = PROMPT_TMPL.render(**ctx)
        response = None
        content = ""
        error_msg = None
        model = "o3"
        for attempt in range(2):
            try:
                response = chat(model=model, messages=[{"role": "user", "content": prompt}], temperature=0)
                content = response.choices[0].message.content
                logging.info(f"[UXAgent] LLM returned design content for task {task_id} (attempt {attempt+1})")
                error_msg = None
                break
            except Exception as exc:
                error_msg = str(exc)
                logging.error(f"[UXAgent] LLM generation failed for task {task_id} (attempt {attempt+1}): {exc}")
                if attempt == 0:
                    Repo(tid).update(task_id, retries=task_obj.retries + 1, notes=error_msg)
                    err = error_msg[:200] + "..." if len(error_msg) > 200 else error_msg
                    ctx["error_note"] = err
                    prompt = PROMPT_TMPL.render(**ctx)
                    model = "o3-pro"
                else:
                    Repo(tid).update(task_id, status="failed", owner="UX/UI", notes=error_msg)
                    PROM_TASK_FAILED.labels(tid).inc()
                    TASK_CNT.labels("ux_ui", "failed").inc()
                    return
        # Artefakt nur bei Erfolg speichern
        save_artefact(task_id, content.encode("utf-8"), filename=f"{task_id}.md")
        tokens_used = 0
        try:
            tokens_used = response.usage.total_tokens if response and hasattr(response, "usage") else 0
        except Exception:
            pass
        Repo(tid).update(task_id, status="done", owner="UX/UI", notes="wireframe", tokens_actual=tokens_used)
    try:
        debit(tid, tokens_used * (TOKEN_PRICE_PER_1000 / 1000.0))
    except Exception as e:
        logging.error(f"[UXAgent] Budget debit failed for task {task_id}: {e}")
    TASK_CNT.labels("ux_ui", "done").inc()
    logging.info(f"[UXAgent] Task {task_id} completed by UX/UI agent (tokens used: {tokens_used})")
