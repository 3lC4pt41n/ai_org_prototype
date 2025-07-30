from __future__ import annotations

import logging
from pathlib import Path

from jinja2 import Template

from ai_org_backend.tasks.celery_app import celery
from ai_org_backend.main import Repo, TASK_CNT, TASK_LAT, debit, TOKEN_PRICE_PER_1000
from ai_org_backend.services.storage import save_artefact
from ai_org_backend.db import SessionLocal
from ai_org_backend.models import Task, Purpose
from ai_org_backend.utils.llm import chat

# Load prompt template for Dev agent
_TMPL_PATH = Path(__file__).resolve().parents[3] / "prompts" / "dev.j2"
PROMPT_TMPL = Template(_TMPL_PATH.read_text(encoding="utf-8"))


@celery.task(name="agent.dev")
def agent_dev(tid: str, task_id: str) -> None:
    """Generate code for the given task using OpenAI."""
    logging.info(f"[DevAgent] Generating code for task {task_id} (tenant {tid})")
    with TASK_LAT.labels("dev").time():
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
            ctx = {
                "purpose": purpose_name,
                "task": task_obj.description,
                "business_value": task_obj.business_value,
                "tokens_plan": task_obj.tokens_plan,
                "purpose_relevance": int((task_obj.purpose_relevance or 0) * 100),
            }
        prompt = PROMPT_TMPL.render(**ctx)
        response = None
        try:
            response = chat(model="o3", messages=[{"role": "user", "content": prompt}], temperature=0)
            content = response.choices[0].message.content
            logging.info(f"[DevAgent] LLM returned content for task {task_id}")
        except Exception as exc:
            content = f"ERROR: {exc}"
            logging.error(f"[DevAgent] LLM generation failed for task {task_id}: {exc}")
        save_artefact(task_id, content.encode("utf-8"), filename=f"{task_id}.py")
        tokens_used = 0
        try:
            tokens_used = response.usage.total_tokens if response and hasattr(response, "usage") else 0
        except Exception:
            pass
        Repo(tid).update(task_id, status="done", owner="Dev", notes="code generated", tokens_actual=tokens_used)
    try:
        debit(tid, tokens_used * (TOKEN_PRICE_PER_1000 / 1000.0))
    except Exception as e:
        logging.error(f"[DevAgent] Budget debit failed for task {task_id}: {e}")
    TASK_CNT.labels("dev", "done").inc()
    logging.info(f"[DevAgent] Task {task_id} completed by Dev agent (tokens used: {tokens_used})")
