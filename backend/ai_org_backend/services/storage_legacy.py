# storage.py – file / artefact pipeline  (v1.0)
# ------------------------------------------------------------
from __future__ import annotations

import hashlib, subprocess, shutil, mimetypes, os
from pathlib import Path
from datetime import datetime as dt
from typing import Optional

from neo4j import GraphDatabase
from sqlmodel import Session, select

from models import Artifact, Task, engine

# ─────────────────── Config ──────────────────────────
WORKSPACE = Path.cwd() / "workspace"               # repo root
WORKSPACE.mkdir(exist_ok=True)

NEO4J_URL  = os.getenv("NEO4J_URL",  "bolt://localhost:7687")
driver     = GraphDatabase.driver(
    NEO4J_URL,
    auth=(os.getenv("NEO4J_USER", "neo4j"),
          os.getenv("NEO4J_PASS", "s3cr3tP@ss"))
)

# ensure workspace is a git repo
if not (WORKSPACE / ".git").exists():
    subprocess.run(["git", "init", "-q", str(WORKSPACE)], check=True)


# ─────────── Helpers ─────────────────────────────────
def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _mime(p: Path) -> str:
    mt, _ = mimetypes.guess_type(p)
    return mt or "application/octet-stream"


def _git_commit(rel_path: str, message: str) -> None:
    subprocess.run(["git", "-C", str(WORKSPACE), "add", rel_path], check=True)
    subprocess.run(
        ["git", "-C", str(WORKSPACE), "commit", "-m", message, "--quiet"],
        check=True,
    )


def _link_neo4j(task_id: str, artefact_sha: str) -> None:
    """
    Create (Task)-[:PRODUCED]->(Artefact {sha256:…}) edge.
    """
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


# ─────────── Public API ──────────────────────────────
def save_artefact(
    task_id: str,
    src: Path | bytes,
    filename: Optional[str] = None,
) -> Artifact:
    """
    Copy *src* (file path **or** bytes) into ./workspace/,
    register DB row, Git-commit & Neo4j edge.
    Returns the persisted `Artifact` row.
    """
    # 1. Normalise input → Path in workspace
    if isinstance(src, bytes):
        if not filename:
            raise ValueError("`filename` required when passing bytes.")
        tgt = WORKSPACE / filename
        tgt.write_bytes(src)
    else:  # Path
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

    # 2. SQL insert
    with Session(engine) as s:
        s.add(artefact)

        # increment tokens_actual heuristically (≈ words * 1.5)
        task: Task | None = s.exec(select(Task).where(Task.id == task_id)).first()
        if task:
            delta = len(tgt.read_text(encoding="utf-8", errors="ignore").split()) * 1.5
            task.tokens_actual += int(delta)

        s.commit()
        s.refresh(artefact)

    # 3. Git & Neo4j
    _git_commit(artefact.repo_path, f"{task_id}: add artefact {artefact.sha256[:8]}")
    _link_neo4j(task_id, sha)

    return artefact


# ─────────── CLI test ─────────────────────────────────
if __name__ == "__main__":
    import sys, textwrap, tempfile

    if len(sys.argv) != 3:
        print(
            textwrap.dedent(
                """\
            Usage: python storage.py <task_id> <file_or_text>
            - If <file_or_text> points to an existing file, it will be copied.
            - Otherwise a temp file with that text will be created."""
            )
        )
        sys.exit(1)

    task_id, arg = sys.argv[1], sys.argv[2]
    p = Path(arg)
    if p.exists():
        art = save_artefact(task_id, p)
    else:
        with tempfile.NamedTemporaryFile(
            mode="w+", suffix=".txt", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(arg)
            tmp.flush()
            art = save_artefact(task_id, Path(tmp.name))
    print(f"✅  stored artefact {art.repo_path} ({art.size} B)")
