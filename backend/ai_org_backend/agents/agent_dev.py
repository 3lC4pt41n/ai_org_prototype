from __future__ import annotations

import logging
from pathlib import Path

from jinja2 import Template

from ai_org_backend.tasks.celery_app import celery
from ai_org_backend.main import Repo, TASK_CNT, TASK_LAT, debit, TOKEN_PRICE_PER_1000
from ai_org_backend.services.storage import save_artefact
from ai_org_backend.db import SessionLocal
from sqlmodel import select
from ai_org_backend.models import Task, Purpose, TaskDependency
from ai_org_backend.utils.llm import chat
from ai_org_backend.orchestrator.inspector import PROM_TASK_FAILED, insights_generated_total

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
        error_msg = None
        try:
            response = chat(model="o3", messages=[{"role": "user", "content": prompt}], temperature=0)
            content = response.choices[0].message.content
            logging.info(f"[DevAgent] LLM returned content for task {task_id}")
        except Exception as exc:
            error_msg = str(exc)
            content = f"ERROR: {exc}"
            logging.error(f"[DevAgent] LLM generation failed for task {task_id}: {exc}")
        save_artefact(task_id, content.encode("utf-8"), filename=f"{task_id}.py")
        tokens_used = 0
        try:
            tokens_used = response.usage.total_tokens if response and hasattr(response, "usage") else 0
        except Exception:
            pass
        if error_msg:
            Repo(tid).update(task_id, status="failed", owner="Dev", notes=error_msg)
            PROM_TASK_FAILED.labels(tid).inc()
            TASK_CNT.labels("dev", "failed").inc()
            return
        # Markiere die aktuelle Task als erledigt und prüfe auf Folgeaufgaben
        Repo(tid).update(task_id, status="done", owner="Dev", notes="code generated", tokens_actual=tokens_used)
        followups = []
        if "```" not in content:
            # Wenn die KI eine Aufzählung statt Code geliefert hat: jeden Punkt als neue Task anlegen
            for line in content.splitlines():
                if line.strip().startswith(("-", "*", "1.", "2.", "3.")):
                    desc = line.lstrip("-*0123456789. ").strip()
                    if desc:
                        followups.append(desc)
        else:
            # Andernfalls nach 'TODO:'-Kommentaren im Code suchen
            import re
            for match in re.finditer(r'TODO[:\s]+(.+)', content):
                desc = match.group(1).strip().rstrip('.:')
                if desc:
                    followups.append(desc)
        if followups:
            with SessionLocal() as session:
                parent = session.get(Task, task_id)
                # Werte für neue Aufgaben bestimmen (Token-Budget aufteilen, Mindestwert 500)
                bv_each = max(round(parent.business_value / len(followups), 1), 0.1)
                tok_each = (parent.tokens_plan // len(followups) if parent.tokens_plan else 0) or 500
                for desc in followups:
                    new_task = Task(tenant_id=tid, purpose_id=parent.purpose_id,
                                    description=desc,
                                    business_value=bv_each,
                                    tokens_plan=tok_each,
                                    purpose_relevance=parent.purpose_relevance,
                                    notes=f"auto-split from task {task_id}")
                    session.add(new_task)
                session.flush()
                # Jede neue Task mit Abhängigkeit (FINISH_START) an die originale Task verknüpfen
                for t in session.query(Task).filter(Task.notes == f"auto-split from task {task_id}").all():
                    session.add(TaskDependency(from_id=task_id, to_id=t.id, dependency_type="FINISH_START"))
                session.commit()
            logging.info(f"[DevAgent] Created {len(followups)} follow-up task(s) from task {task_id}")
            insights_generated_total.inc(len(followups))
            try:
                from scripts.seed_graph import ingest
                ingest(tid)
            except Exception as e:
                logging.error(f"[DevAgent] Neo4j ingest failed: {e}")
    try:
        debit(tid, tokens_used * (TOKEN_PRICE_PER_1000 / 1000.0))
    except Exception as e:
        logging.error(f"[DevAgent] Budget debit failed for task {task_id}: {e}")
    TASK_CNT.labels("dev", "done").inc()
    logging.info(f"[DevAgent] Task {task_id} completed by Dev agent (tokens used: {tokens_used})")
