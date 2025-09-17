from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from ai_org_backend.db import SessionLocal
from ai_org_backend.main import TASK_CNT, TASK_LAT, TOKEN_PRICE_PER_1000, Repo, debit
from ai_org_backend.models import Purpose, Task, TaskDependency, Tenant
from ai_org_backend.models.chat import ChatRole
from ai_org_backend.orchestrator.inspector import PROM_TASK_FAILED, insights_generated_total
from ai_org_backend.services.budget import BudgetExceededError
from ai_org_backend.services.deep_research import run_deep_research
from ai_org_backend.services.llm_client import MODEL_DEFAULT, MODEL_THINKING, chat_with_tools
from ai_org_backend.services.storage import driver, save_artefact
from ai_org_backend.settings import settings
from ai_org_backend.tasks.celery_app import celery
from ai_org_backend.utils.filetypes import infer_extension, strip_code_fences

from .utils import load_template

# Unified number of retry attempts for LLM errors
MAX_AGENT_RETRIES = 2

# Load prompt template for Dev agent
PROMPT_TMPL = load_template("dev.j2")

WORKSPACE_ROOT = settings.workspace_dir


@celery.task(name="agent.dev")
def agent_dev(tid: str, task_id: str) -> None:
    """Generate code for the given task using OpenAI."""
    logging.info(f"[DevAgent] Generating code for task {task_id} (tenant {tid})")
    with TASK_LAT.labels("dev", tid).time():
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

            tenant = session.get(Tenant, tid)
            allow_research = bool(tenant and tenant.allow_web_research)

            ctx = {
                "purpose": purpose_name,
                "task": task_obj.description,
                "business_value": task_obj.business_value,
                "tokens_plan": task_obj.tokens_plan,
                "purpose_relevance": int((task_obj.purpose_relevance or 0) * 100),
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

            trigger_keywords = (
                "integrate",
                "sdk",
                "oauth",
                "stripe",
                "webhook",
                "kafka",
                "docker",
                "helm",
                "mongodb",
                "cassandra",
                "redis stream",
            )
            need_research = any(k in task_obj.description.lower() for k in trigger_keywords)
            research_note = ""
            if allow_research and need_research:
                q = (
                    f"Give me the safest and most up-to-date way to: {task_obj.description}. "
                    "Return concrete code-level hints and recommended libraries with versions."
                )
                research = run_deep_research(tid, q, model=MODEL_THINKING)
                research_note = research["summary"][:2000]
            if research_note:
                memory_snippets.insert(
                    0, {"category": "research", "source": "web", "chunk": research_note}
                )

            ctx["memory_snippets"] = memory_snippets
        prompt = PROMPT_TMPL.render(**ctx)
        response = None
        content = ""
        error_msg = None
        model = MODEL_DEFAULT
        for attempt in range(MAX_AGENT_RETRIES + 1):
            try:
                response = chat_with_tools(
                    messages=[{"role": ChatRole.USER.value, "content": prompt}],
                    model=model,
                    temperature=0,
                    tenant_id=tid,
                    usage_label="dev",
                )
                content = response["choices"][0]["message"]["content"]
                logging.info(
                    f"[DevAgent] LLM returned content for task {task_id} (attempt {attempt+1})"
                )
                error_msg = None
                break
            except BudgetExceededError:
                Repo(tid).update(
                    task_id,
                    status="budget_exceeded",
                    owner="Dev",
                    notes="Budget exhausted. Please top up and retry.",
                )
                return
            except Exception as exc:
                error_msg = str(exc)
                logging.error(
                    "[DevAgent] LLM generation failed for task %s (attempt %s): %s",
                    task_id,
                    attempt + 1,
                    exc,
                )
                if attempt < MAX_AGENT_RETRIES:
                    Repo(tid).update(
                        task_id,
                        retries=task_obj.retries + 1,
                        notes="LLM error: " + error_msg,
                    )
                    err_note = error_msg[:200] + "..." if len(error_msg) > 200 else error_msg
                    ctx["error_note"] = err_note
                    prompt = PROMPT_TMPL.render(**ctx)
                    model = MODEL_THINKING
                else:
                    Repo(tid).update(task_id, status="failed", owner="Dev", notes=error_msg)
                    PROM_TASK_FAILED.labels(tid).inc()
                    TASK_CNT.labels(tid, "dev", "failed").inc()
                    return
        # Save artefact only on successful LLM output
        overwrite_flag = "allow_overwrite" in (task_obj.notes or "")
        files: list[tuple[str, str]] = []
        code_texts: list[str] = []
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                fname = data.get("filename") or data.get("path")
                code_text = data.get("content", "")
                if fname:
                    files.append((fname, code_text))
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        fname = item.get("filename") or item.get("path")
                        code_text = item.get("content", "")
                        if fname:
                            files.append((fname, code_text))
        except Exception:
            logging.warning(f"[DevAgent] Non-JSON output for task {task_id}; applying heuristics")
        if not files:
            code_text = strip_code_fences(content)
            ext = infer_extension(code_text)
            fname = f"{task_id}{ext}"
            files.append((fname, code_text))
        saved_files: list[str] = []
        for fname, code_text in files:
            code_text = code_text or content
            code_texts.append(code_text)
            ext = Path(fname).suffix or infer_extension(code_text)
            base_map = {
                ".py": "backend",
                ".html": "frontend",
                ".ts": "frontend",
                ".tsx": "frontend",
                ".jsx": "frontend",
                ".js": "frontend",
                ".css": "styles",
                ".scss": "styles",
            }
            base = base_map.get(ext, "backend")
            if not fname.startswith(f"{base}/") and not Path(fname).is_absolute():
                fname = f"{base}/{fname}"
            file_path = Path(fname)
            if file_path.parent and str(file_path.parent) != ".":
                target_dir = WORKSPACE_ROOT / tid / file_path.parent
                target_dir.mkdir(parents=True, exist_ok=True)
            logging.info(f"[DevAgent] Saving generated code to '{fname}' for task {task_id}")
            save_artefact(
                task_id,
                code_text.encode("utf-8"),
                filename=fname,
                allow_overwrite=overwrite_flag,
            )
            saved_files.append(fname)
        tokens_used = 0
        try:
            tokens_used = (
                response.usage.total_tokens if response and hasattr(response, "usage") else 0
            )
        except Exception as e:
            logging.debug("Failed to retrieve token usage for task %s: %s", task_id, e)
            tokens_used = 0
        # Mark the current task as done and check for follow-up tasks
        Repo(tid).update(
            task_id,
            status="done",
            owner="Dev",
            notes="code generated",
            tokens_actual=tokens_used,
        )
        combined_code = "\n".join(code_texts)
        followups = []
        if not code_texts:
            logging.info(
                f"[DevAgent] Output was a list for task {task_id}; splitting into sub-tasks"
            )
            # If the AI returned a list instead of code: create a new task for each item
            for line in content.splitlines():
                if line.strip().startswith(("-", "*", "1.", "2.", "3.")):
                    desc = line.lstrip("-*0123456789. ").strip()
                    if desc:
                        followups.append(desc)
        else:
            for match in re.finditer(r"TODO[:\s]+(.+)", combined_code):
                desc = match.group(1).strip().rstrip(".:")
                if desc:
                    followups.append(desc)
        if followups:
            with SessionLocal() as session:
                parent = session.get(Task, task_id)
                # Determine values for new tasks (split token budget, minimum 500)
                bv_each = max(round(parent.business_value / len(followups), 1), 0.1)
                tok_each = (
                    parent.tokens_plan // len(followups) if parent.tokens_plan else 0
                ) or 500
                for desc in followups:
                    new_task = Task(
                        tenant_id=tid,
                        purpose_id=parent.purpose_id,
                        description=desc,
                        business_value=bv_each,
                        tokens_plan=tok_each,
                        purpose_relevance=parent.purpose_relevance,
                        notes=f"auto-split from task {task_id}",
                    )
                    session.add(new_task)
                session.flush()  # IDs zuweisen
                # Link each new task as a FINISH_START dependency with the original task
                for t in (
                    session.query(Task)
                    .filter(Task.notes == f"auto-split from task {task_id}")
                    .all()
                ):
                    session.add(
                        TaskDependency(from_id=task_id, to_id=t.id, dependency_type="FINISH_START")
                    )
                session.commit()
            logging.info(
                f"[DevAgent] Created {len(followups)} follow-up task(s) from task {task_id}"
            )
            insights_generated_total.inc(len(followups))
            # Update Neo4j graph with new tasks and dependencies (incremental sync)
            try:
                with SessionLocal() as session2:
                    new_tasks = (
                        session2.query(Task)
                        .filter(Task.notes == f"auto-split from task {task_id}")
                        .all()
                    )
                with driver.session() as g:
                    for t_obj in new_tasks:
                        g.run(
                            """MERGE (t:Task {id:$id}) SET t.desc=$desc, t.status=$status""",
                            id=t_obj.id,
                            desc=t_obj.description,
                            status=str(t_obj.status),
                        )
                        g.run(
                            """MATCH (p:Task {id:$pid}), (c:Task {id:$cid})
                                 MERGE (p)-[:DEPENDS_ON {kind:'FINISH_START'}]->(c)""",
                            pid=task_id,
                            cid=t_obj.id,
                        )
            except Exception as e:
                logging.error(f"[DevAgent] Neo4j graph update failed: {e}")
    try:
        debit(
            tid,
            tokens_used * (TOKEN_PRICE_PER_1000 / 1000.0),
            task_obj.purpose_id,
        )
    except Exception as e:
        logging.error(f"[DevAgent] Budget debit failed for task {task_id}: {e}")
    TASK_CNT.labels(tid, "dev", "done").inc()
    logging.info(f"[DevAgent] Task {task_id} completed by Dev agent (tokens used: {tokens_used})")
