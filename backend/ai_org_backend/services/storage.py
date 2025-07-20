from __future__ import annotations

import hashlib
import mimetypes
from datetime import datetime as dt
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from neo4j import GraphDatabase
from sqlmodel import Session, select

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


def save_artefact(task_id: str, src: Path | bytes, filename: Optional[str] = None) -> Artifact:
    if isinstance(src, bytes):
        if not filename:
            raise ValueError("`filename` required when passing bytes.")
        tgt = WORKSPACE / filename
        tgt.write_bytes(src)
    else:
        src = Path(src).expanduser().resolve()
        tgt = WORKSPACE / (filename or src.name)
        shutil.copy2(src, tgt)

    sha = _sha256(tgt)
    artefact = Artifact(
        task_id=task_id,
        repo_path=str(tgt.relative_to(WORKSPACE)),
        media_type=_mime(tgt),
        size=tgt.stat().st_size,
        sha256=sha,
    )
    with Session(engine) as s:
        s.add(artefact)
        task: Task | None = s.exec(select(Task).where(Task.id == task_id)).first()
        if task:
            delta = len(tgt.read_text(encoding="utf-8", errors="ignore").split()) * 1.5
            task.tokens_actual += int(delta)
        s.commit()
        s.refresh(artefact)
    _git_commit(artefact.repo_path, f"{task_id}: add artefact {artefact.sha256[:8]}")
    _link_neo4j(task_id, sha)
    return artefact
