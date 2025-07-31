from __future__ import annotations

import logging
from pathlib import Path

from jinja2 import Template

from ai_org_backend.tasks.celery_app import celery
from ai_org_backend.main import Repo, TASK_CNT, TASK_LAT, debit, TOKEN_PRICE_PER_1000
from ai_org_backend.services.storage import save_artefact
from ai_org_backend.db import SessionLocal
from sqlmodel import select
from ai_org_backend.models import Task, Purpose, TaskDependency, Artifact
from ai_org_backend.utils.llm import chat
from ai_org_backend.metrics import prom_counter
from ai_org_backend.orchestrator.inspector import PROM_TASK_FAILED

# Load prompt template for QA agent
_TMPL_PATH = Path(__file__).resolve().parents[3] / "prompts" / "qa.j2"
PROMPT_TMPL = Template(_TMPL_PATH.read_text(encoding="utf-8"))
QA_ARTIFACT_COUNTER = prom_counter("ai_qa_artifact_refs_total", "QA tasks referencing dev artifacts")


@celery.task(name="agent.qa")
def agent_qa(tid: str, task_id: str) -> None:
    """Generate a QA test report for the task using OpenAI."""
    logging.info(f"[QAAgent] Starting QA review for task {task_id} (tenant {tid})")
    with TASK_LAT.labels("qa").time():
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
            }
            # Attach code artefact snippet from preceding Dev task if available
            dep = session.exec(select(TaskDependency).where(TaskDependency.to_id == task_id, TaskDependency.dependency_type == "FINISH_START")).first()
            dev_task_id = dep.from_id if dep else None
            if dev_task_id:
                artifacts = session.exec(select(Artifact).where(Artifact.task_id == dev_task_id)).all()
                if not artifacts:
                    logging.warning(f"[QAAgent] Dev artefact missing for task {dev_task_id}, skipping QA for task {task_id}")
                    Repo(tid).update(task_id, status="skipped", owner="QA", notes="no dev artefact")
                    PROM_TASK_FAILED.labels(tid).inc()
                    TASK_CNT.labels("qa", "failed").inc()
                    return
                snippets = []
                for artefact in artifacts:
                    file_path = Path("workspace") / tid / artefact.repo_path
                    try:
                        code_content = file_path.read_text(encoding="utf-8")
                    except Exception as e:
                        logging.error(f"[QAAgent] Failed to read artefact file {file_path}: {e}")
                        code_content = ""
                    if not code_content:
                        continue
                    # Extract snippet (full or partial) from artefact content
                    MAX_TOKENS = 800
                    if len(code_content) <= MAX_TOKENS * 4:
                        snippet_content = code_content
                    else:
                        lines = code_content.splitlines()
                        snippet_lines = []
                        for ln in lines:
                            lstripped = ln.lstrip()
                            if lstripped.startswith("def ") or lstripped.startswith("class ") or "TODO" in ln or "todo" in ln:
                                snippet_lines.append(ln)
                        if not snippet_lines:
                            snippet_lines = lines[:50]
                        snippet_content = "\n".join(snippet_lines)
                    ext = Path(artefact.repo_path).suffix.lower()
                    if ext == ".py":
                        snippet_lang = "python"
                    elif ext == ".js":
                        snippet_lang = "javascript"
                    elif ext == ".ts":
                        snippet_lang = "typescript"
                    elif ext in [".jsx", ".tsx"]:
                        snippet_lang = "jsx"
                    elif ext in [".html", ".htm"]:
                        snippet_lang = "html"
                    elif ext == ".css":
                        snippet_lang = "css"
                    elif ext == ".json":
                        snippet_lang = "json"
                    else:
                        snippet_lang = ""
                    snippets.append({"filename": artefact.repo_path, "content": snippet_content, "language": snippet_lang})
                if snippets:
                    ctx["snippets"] = snippets
                    logging.info(f"[QAAgent] Attached code snippets from task {dev_task_id} into QA prompt for task {task_id} ({len(snippets)} file(s))")
                    QA_ARTIFACT_COUNTER.inc(len(snippets))
                else:
                    logging.warning(f"[QAAgent] No readable code artifacts for task {dev_task_id}, skipping QA for task {task_id}")
                    Repo(tid).update(task_id, status="skipped", owner="QA", notes="no dev artefact")
                    PROM_TASK_FAILED.labels(tid).inc()
                    TASK_CNT.labels("qa", "failed").inc()
                    return
            else:
                logging.warning(f"[QAAgent] No preceding dev task found for task {task_id}, skipping QA")
                Repo(tid).update(task_id, status="skipped", owner="QA", notes="no dev task")
                PROM_TASK_FAILED.labels(tid).inc()
                TASK_CNT.labels("qa", "failed").inc()
                return
        prompt = PROMPT_TMPL.render(**ctx)
        response = None
        error_msg = None
        try:
            response = chat(model="o3", messages=[{"role": "user", "content": prompt}], temperature=0)
            content = response.choices[0].message.content
            logging.info(f"[QAAgent] LLM returned QA report for task {task_id}")
        except Exception as exc:
            error_msg = str(exc)
            content = f"ERROR: {exc}"
            logging.error(f"[QAAgent] LLM generation failed for task {task_id}: {exc}")
        save_artefact(task_id, content.encode("utf-8"), filename=f"{task_id}_qa.txt")
        tokens_used = 0
        try:
            tokens_used = response.usage.total_tokens if response and hasattr(response, "usage") else 0
        except Exception:
            pass
        if error_msg:
            Repo(tid).update(task_id, status="failed", owner="QA", notes=error_msg)
            PROM_TASK_FAILED.labels(tid).inc()
            TASK_CNT.labels("qa", "failed").inc()
            return
        Repo(tid).update(task_id, status="done", owner="QA", notes="QA report", tokens_actual=tokens_used)
    try:
        debit(tid, tokens_used * (TOKEN_PRICE_PER_1000 / 1000.0))
    except Exception as e:
        logging.error(f"[QAAgent] Budget debit failed for task {task_id}: {e}")
    TASK_CNT.labels("qa", "done").inc()
    logging.info(f"[QAAgent] Task {task_id} completed by QA agent (tokens used: {tokens_used})")
