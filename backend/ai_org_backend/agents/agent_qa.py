from __future__ import annotations

import logging
from pathlib import Path

from jinja2 import Template

from ai_org_backend.tasks.celery_app import celery
from ai_org_backend.main import Repo, TASK_CNT, TASK_LAT, debit, TOKEN_PRICE_PER_1000
from ai_org_backend.services.storage import save_artefact
from ai_org_backend.services.testing import run_tests
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
        content = ""
        error_msg = None
        model = "o3"
        for attempt in range(2):
            try:
                response = chat(model=model, messages=[{"role": "user", "content": prompt}], temperature=0)
                content = response.choices[0].message.content
                logging.info(f"[QAAgent] LLM returned QA report for task {task_id} (attempt {attempt+1})")
                error_msg = None
                break
            except Exception as exc:
                error_msg = str(exc)
                logging.error(f"[QAAgent] LLM generation failed for task {task_id} (attempt {attempt+1}): {exc}")
                if attempt == 0:
                    Repo(tid).update(task_id, retries=task_obj.retries + 1, notes=error_msg)
                    err = error_msg[:200] + "..." if len(error_msg) > 200 else error_msg
                    ctx["error_note"] = err
                    prompt = PROMPT_TMPL.render(**ctx)
                    model = "o3-pro"
                else:
                    Repo(tid).update(task_id, status="failed", owner="QA", notes=error_msg)
                    PROM_TASK_FAILED.labels(tid).inc()
                    TASK_CNT.labels("qa", "failed").inc()
                    return
        # QA-Report nur bei Erfolg speichern
        save_artefact(task_id, content.encode("utf-8"), filename=f"{task_id}_qa.txt")
        tokens_used = 0
        try:
            tokens_used = response.usage.total_tokens if response and hasattr(response, "usage") else 0
        except Exception:
            pass
        # Run any generated tests with pytest in an isolated workspace
        with SessionLocal() as session:
            test_artifacts = session.exec(
                select(Artifact).where(Artifact.task_id == task_id, Artifact.repo_path.ilike("test%.py"))
            ).all()

        if test_artifacts:
            logging.info(
                f"[QAAgent] Detected {len(test_artifacts)} test file(s) for task {task_id}, executing pytest"
            )
            test_paths = []
            for art in test_artifacts:
                art_path = Path(art.repo_path)
                if art_path.parts and art_path.parts[0] == tid:
                    art_path = Path(*art_path.parts[1:])
                test_paths.append(str(art_path))
            tests_passed, test_output = run_tests(tid, test_paths)
            save_artefact(task_id, test_output.encode("utf-8"), filename=f"{task_id}_test_results.txt")
            if tests_passed:
                Repo(tid).update(
                    task_id,
                    status="done",
                    owner="QA",
                    notes="QA report - tests passed",
                    tokens_actual=tokens_used,
                )
                logging.info(f"[QAAgent] All tests passed for task {task_id}")
            else:
                Repo(tid).update(
                    task_id,
                    status="failed",
                    owner="QA",
                    notes="QA report - tests failed",
                    tokens_actual=tokens_used,
                )
                logging.warning(
                    f"[QAAgent] Test failures detected for task {task_id}, creating fix task"
                )
                fail_lines = [
                    line.strip() for line in test_output.splitlines() if line.strip().startswith("FAILED ")
                ]
                if fail_lines:
                    if len(fail_lines) == 1:
                        new_desc = f"Fix failing test: {fail_lines[0][len('FAILED '):]}"
                    else:
                        failures_list = "\n".join(f"- {line[len('FAILED '):]}" for line in fail_lines)
                        new_desc = f"Fix failing tests:\n{failures_list}"
                else:
                    new_desc = "Fix issues causing test failure"
                with SessionLocal() as session:
                    parent_task = session.get(Task, task_id)
                    orig_dev_task = session.get(Task, dev_task_id) if dev_task_id else None
                    biz_value = (
                        orig_dev_task.business_value if orig_dev_task else parent_task.business_value
                    )
                    plan_tokens = (
                        orig_dev_task.tokens_plan if orig_dev_task and orig_dev_task.tokens_plan else 0
                    ) or 500
                    fix_task = Task(
                        tenant_id=tid,
                        purpose_id=parent_task.purpose_id,
                        description=new_desc,
                        business_value=biz_value,
                        tokens_plan=plan_tokens,
                        purpose_relevance=parent_task.purpose_relevance,
                        notes=f"auto-generated from QA task {task_id}",
                    )
                    session.add(fix_task)
                    session.flush()
                    session.add(
                        TaskDependency(from_id=task_id, to_id=fix_task.id, dependency_type="FINISH_START")
                    )
                    session.commit()
                    new_task_id = fix_task.id
                logging.info(
                    f"[QAAgent] Created new Dev task {new_task_id} to address test failures from task {task_id}"
                )
                try:
                    from scripts.seed_graph import ingest
                    ingest(tid)
                except Exception as e:
                    logging.error(f"[QAAgent] Neo4j ingest failed for new task {new_task_id}: {e}")
        else:
            logging.warning(f"[QAAgent] No tests found for task {task_id}")
            no_test_msg = "no tests detected"
            save_artefact(task_id, no_test_msg.encode("utf-8"), filename=f"{task_id}_test_results.txt")
            Repo(tid).update(
                task_id,
                status="failed",
                owner="QA",
                notes="QA report - no tests",
                tokens_actual=tokens_used,
            )
            with SessionLocal() as session:
                parent_task = session.get(Task, task_id)
                orig_dev_task = session.get(Task, dev_task_id) if dev_task_id else None
                biz_value = orig_dev_task.business_value if orig_dev_task else parent_task.business_value
                plan_tokens = (
                    orig_dev_task.tokens_plan if orig_dev_task and orig_dev_task.tokens_plan else 0
                ) or 500
                new_desc = f"Add tests: {parent_task.description}"
                fix_task = Task(
                    tenant_id=tid,
                    purpose_id=parent_task.purpose_id,
                    description=new_desc,
                    business_value=biz_value,
                    tokens_plan=plan_tokens,
                    purpose_relevance=parent_task.purpose_relevance,
                    notes=f"auto-generated from QA task {task_id}",
                )
                session.add(fix_task)
                session.flush()
                session.add(
                    TaskDependency(from_id=task_id, to_id=fix_task.id, dependency_type="FINISH_START")
                )
                session.commit()
                new_task_id = fix_task.id
            logging.info(
                f"[QAAgent] Created new Dev task {new_task_id} to add missing tests for task {task_id}"
            )
            try:
                from scripts.seed_graph import ingest
                ingest(tid)
            except Exception as e:
                logging.error(f"[QAAgent] Neo4j ingest failed for new task {new_task_id}: {e}")
    try:
        debit(tid, tokens_used * (TOKEN_PRICE_PER_1000 / 1000.0))
    except Exception as e:
        logging.error(f"[QAAgent] Budget debit failed for task {task_id}: {e}")
    TASK_CNT.labels("qa", "done").inc()
    logging.info(f"[QAAgent] Task {task_id} completed by QA agent (tokens used: {tokens_used})")
