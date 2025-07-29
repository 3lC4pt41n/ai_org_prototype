from __future__ import annotations

import hashlib
import mimetypes
from datetime import datetime as dt
import os
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from neo4j import GraphDatabase
from sqlmodel import Session

from ai_org_backend.db import engine
from ai_org_backend.models import Artifact, Task

WORKSPACE = Path.cwd() / "workspace"
WORKSPACE.mkdir(exist_ok=True)

NEO4J_URL = os.getenv("NEO4J_URL", "bolt://localhost:7687")
driver = GraphDatabase.driver(
    NEO4J_URL,
    auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASS", "s3cr3tP@ss")),
)

if not (WORKSPACE / ".git").exists():
    subprocess.run(["git", "init", "-q", str(WORKSPACE)], check=True)


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _mime(p: Path) -> str:
    mt, _ = mimetypes.guess_type(p)
    return mt or "application/octet-stream"


def _git_commit(rel_path: str, message: str) -> None:
    subprocess.run(["git", "-C", str(WORKSPACE), "add", rel_path], check=True)
    subprocess.run([
        "git",
        "-C",
        str(WORKSPACE),
        "commit",
        "-m",
        message,
        "--quiet",
    ], check=True)


def _link_neo4j(task_id: str, artefact_sha: str) -> None:
    with driver.session() as g:
        g.run(
            """
            MERGE (a:Artifact {sha256:$sha})
              ON CREATE SET a.created_at=$ts
            MATCH (t:Task {id:$tid})
            MERGE (t)-[:PRODUCED]->(a)
            """,
            sha=artefact_sha,
            ts=dt.utcnow().isoformat(),
            tid=task_id,
        )


def register_artefact(task_id: str, src: Path | bytes, filename: Optional[str] = None) -> Artifact:
    """Save artefact file for a completed task and register it in the database.
    Automatically stores the artefact under the tenant's workspace directory and records metadata."""
    # Determine tenant workspace directory
    with Session(engine) as session:
        task_obj = session.get(Task, task_id)
        tenant_dir = task_obj.tenant_id if task_obj else "default"
    target_dir = WORKSPACE / tenant_dir
    target_dir.mkdir(exist_ok=True, parents=True)
    # Determine target file path and ensure unique name
    if isinstance(src, bytes):
        if not filename:
            raise ValueError("`filename` required when passing bytes.")
        base_name = filename
    else:
        src = Path(src).expanduser().resolve()
        base_name = filename or src.name
    tgt = target_dir / base_name
    original_tgt = tgt
    counter = 1
    while tgt.exists():
        stem = original_tgt.stem
        suffix = original_tgt.suffix
        tgt = target_dir / f"{stem}_{counter}{suffix}"
        counter += 1
    # Write bytes or copy file
    if isinstance(src, bytes):
        tgt.write_bytes(src)
    else:
        shutil.copy2(src, tgt)

    # Compute metadata
    sha = _sha256(tgt)
    artefact = Artifact(
        task_id=task_id,
        repo_path=str(tgt.relative_to(WORKSPACE)),
        media_type=_mime(tgt),
        size=tgt.stat().st_size,
        sha256=sha,
    )
    # Save artefact in database and link to task
    with Session(engine) as session:
        session.add(artefact)
        task_obj = session.get(Task, task_id)
        if task_obj:
            # Update token usage (approximate)
            try:
                text_content = tgt.read_text(encoding="utf-8", errors="ignore")
                word_count = len(text_content.split())
            except Exception:
                word_count = 0
            task_obj.tokens_actual += int(word_count * 1.5)
        session.commit()
        session.refresh(artefact)
    _git_commit(artefact.repo_path, f"{task_id}: add artefact {artefact.sha256[:8]}")
    _link_neo4j(task_id, sha)
    logging.info(f"Registered artefact for Task {task_id}: {artefact.repo_path} (SHA256={sha[:8]})")
    return artefact

# Maintain backward compatibility
save_artefact = register_artefact
