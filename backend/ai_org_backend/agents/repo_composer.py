"""Celery agent to compose an initial repository structure based on the architecture plan."""
from __future__ import annotations

import logging
from pathlib import Path
from jinja2 import Template

# Import Celery app and utilities
from ai_org_backend.tasks.celery_app import celery
from ai_org_backend.services.storage import save_artefact
from ai_org_backend.main import Repo, TASK_CNT, TASK_LAT, debit, TOKEN_PRICE_PER_1000
from ai_org_backend.db import SessionLocal
from ai_org_backend.models import Task, Artifact
from ai_org_backend.utils.llm import chat
from ai_org_backend.orchestrator.inspector import PROM_TASK_FAILED

# Load prompt template for repository composition
_TMPL_PATH = Path(__file__).resolve().parents[3] / "prompts" / "repo_composer.j2"
PROMPT_TMPL = Template(_TMPL_PATH.read_text(encoding="utf-8"))


@celery.task(name="agent.repo")
def agent_repo(tenant_id: str, task_id: str) -> None:
    """Generate initial project repository scaffolding (folders, files, CI stubs) and save as artefacts."""
    logging.info(f"[repo_composer] Starting repo scaffolding for Task {task_id} (tenant {tenant_id})")
    with TASK_LAT.labels("repo").time():
        # Retrieve architecture plan from task or related artefact
        architecture_plan = ""
        with SessionLocal() as db:
            task_obj = db.get(Task, task_id)
            if task_obj:
                # Try to find a related architecture blueprint artefact (if any)
                artefact = db.query(Artifact).join(Task).filter(
                    Task.purpose_id == task_obj.purpose_id,
                    Task.description.ilike("%architecture blueprint%")
                ).first()
                if artefact:
                    # Read blueprint content from workspace file
                    artefact_path = Path("workspace") / task_obj.tenant_id / artefact.repo_path
                    try:
                        architecture_plan = artefact_path.read_text(encoding="utf-8")
                        logging.info(f"[repo_composer] Loaded architecture plan from artefact {artefact.repo_path}")
                    except Exception as e:
                        logging.warning(f"[repo_composer] Failed to read blueprint artefact: {e}")
                # Fallback to task description if no artefact found
                if not architecture_plan:
                    architecture_plan = task_obj.description or ""
            else:
                logging.warning(f"[repo_composer] Task {task_id} not found in DB; proceeding with empty plan.")
        # Render prompt and call LLM to generate repository scaffold
        prompt = PROMPT_TMPL.render(architecture_plan=architecture_plan)
        response = None
        error_msg = None
        try:
            response = chat(model="o3", messages=[{"role": "user", "content": prompt}], temperature=0)
            content = response.choices[0].message.content
            logging.info(f"[repo_composer] LLM generated scaffold for Task {task_id}")
        except Exception as exc:
            error_msg = str(exc)
            content = f"ERROR: Failed to generate repository scaffold - {exc}"
            logging.error(f"[repo_composer] LLM generation failed: {exc}")
        # Record tokens used by LLM
        tokens_used = 0
        try:
            tokens_used = response.usage.total_tokens if response and hasattr(response, 'usage') else 0
        except Exception:
            pass
        # Expect LLM to return JSON with files list; try parsing if possible
        files_created = 0
        try:
            import json
            data = json.loads(content)
            files = data.get("files", []) if isinstance(data, dict) else []
        except Exception:
            # If JSON parsing fails, treat entire content as a single README file
            files = [{"path": "README.md", "content": content}]
        # Save each generated file as an artefact
        for file_info in files:
            path = file_info.get("path") or "output.txt"
            file_content = file_info.get("content", "")
            # Ensure subdirectories exist
            file_path = Path(path)
            if file_path.parent and str(file_path.parent) != ".":
                target_dir = Path("workspace") / tenant_id / file_path.parent
                target_dir.mkdir(parents=True, exist_ok=True)
            save_artefact(task_id, file_content.encode("utf-8"), filename=path)
            files_created += 1
        # Mark task as done and assign to Repo owner
        if error_msg:
            Repo(tenant_id).update(task_id, status="failed", owner="Repo", notes=error_msg)
            PROM_TASK_FAILED.labels(tenant_id).inc()
            TASK_CNT.labels("repo", "failed").inc()
            return
        Repo(tenant_id).update(task_id, status="done", owner="Repo", notes=f"{files_created} file(s) created", tokens_actual=tokens_used)
    try:
        debit(tenant_id, tokens_used * (TOKEN_PRICE_PER_1000 / 1000.0))
    except Exception as e:
        logging.error(f"[repo_composer] Budget debit failed for task {task_id}: {e}")
    TASK_CNT.labels("repo", "done").inc()
    logging.info(f"[repo_composer] Completed repo scaffolding for Task {task_id}: {files_created} file(s) saved")
