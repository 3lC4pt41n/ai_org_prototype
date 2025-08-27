from __future__ import annotations

import hashlib
import logging
import mimetypes
import os
import shutil
import subprocess
import time
from datetime import datetime as dt
from pathlib import Path
from typing import Optional

from neo4j import GraphDatabase
from sqlmodel import Session

from ai_org_backend.db import engine
from ai_org_backend.metrics import prom_counter
from ai_org_backend.models import Artifact, Task

from .vector_store import VectorStore

WORKSPACE = Path.cwd() / "workspace"
WORKSPACE.mkdir(exist_ok=True)

NEO4J_URL = os.getenv("NEO4J_URL", "bolt://localhost:7687")
driver = GraphDatabase.driver(
    NEO4J_URL,
    auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASS")),
)

vector_store = VectorStore()
ARTIFACT_UPDATES = prom_counter(
    "ai_artifact_updates_total", "Count of artefacts overwritten via register_artefact"
)

# retry settings for vector persistence
VECTOR_STORE_RETRIES = 3

# Git-Repository im Workspace initialisieren, falls möglich
if WORKSPACE.exists():
    if not (WORKSPACE / ".git").exists():
        try:
            subprocess.run(["git", "init", "-q", str(WORKSPACE)], check=True)
        except Exception as exc:
            logging.getLogger(__name__).warning("Git repository initialization failed: %s", exc)
else:
    logging.getLogger(__name__).warning(
        "Workspace directory %s not found, skipping Git init", WORKSPACE
    )


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _mime(p: Path) -> str:
    mt, _ = mimetypes.guess_type(p)
    return mt or "application/octet-stream"


def _git_commit(rel_path: str, message: str) -> None:
    subprocess.run(["git", "-C", str(WORKSPACE), "add", rel_path], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(WORKSPACE),
            "commit",
            "-m",
            message,
            "--quiet",
        ],
        check=True,
    )


def _link_neo4j(task_id: str, artefact_sha: str) -> None:
    """Link artifact to task in Neo4j graph, ensuring both nodes and relation exist."""
    try:
        # Ensure the task exists in graph (merge on id). Fetch task info for meaningful properties.
        with Session(engine) as session:
            task_obj = session.get(Task, task_id)
            t_status = str(task_obj.status) if task_obj else "todo"
            t_desc = task_obj.description if task_obj else ""
        with driver.session() as g:
            g.run(
                """
                MERGE (t:Task {id:$tid})
                  ON CREATE SET t.status=$status, t.desc=$desc, t.created_at=$ts
                MERGE (a:Artifact {sha256:$sha})
                  ON CREATE SET a.created_at=$ts
                MERGE (t)-[:PRODUCED]->(a)
                """,
                tid=task_id,
                sha=artefact_sha,
                status=t_status,
                desc=t_desc[:200],
                ts=dt.utcnow().isoformat(),
            )
    except Exception as exc:
        logging.getLogger(__name__).error(
            f"Neo4j link failed for Task {task_id}, Artifact {artefact_sha[:8]}: {exc}"
        )


def should_embed(text: str) -> bool:
    """Return True if the given text content should be embedded (not an irrelevant artifact)."""
    # Exclude very short or empty content (e.g., stubs or less than 20 words) from embedding
    if not text:
        return False
    word_count = len(text.split())
    return word_count >= 20


def register_artefact(
    task_id: str,
    src: Path | bytes,
    filename: Optional[str] = None,
    *,
    allow_overwrite: bool = False,
    media_type: Optional[str] = None,
) -> Artifact:
    """Save artefact file for a completed task and register it in the database.
    If ``allow_overwrite`` is True and a file with the same name already exists in the
    tenant workspace, the existing file is replaced instead of creating a suffixed copy.
    Automatically stores the artefact under the tenant's workspace directory and records metadata.
    """
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
    base_name = (base_name or "artifact").strip().lstrip("/\\")
    if (
        not Path(base_name).suffix
        and media_type in ("text/markdown", "text/x-markdown")
    ):
        base_name = f"{base_name}.md"
    tgt = target_dir / base_name
    # Ensure directories exist for nested paths like "requirements/"
    tgt.parent.mkdir(parents=True, exist_ok=True)
    original_exists = tgt.exists()
    if tgt.exists() and not allow_overwrite:
        original_tgt = tgt
        counter = 1
        while tgt.exists():
            stem = original_tgt.stem
            suffix = original_tgt.suffix
            tgt = target_dir / f"{stem}_{counter}{suffix}"
            counter += 1
        original_exists = False
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
        media_type=media_type or _mime(tgt),
        size=tgt.stat().st_size,
        sha256=sha,
    )
    text_content: Optional[str] = None
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
    if original_exists and allow_overwrite and vector_store.client:
        try:
            from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue

            vector_store.client.set_payload(
                collection_name=vector_store.collection_name,
                points_selector=FilterSelector(
                    filter=Filter(
                        must=[
                            FieldCondition(key="tenant", match=MatchValue(value=tenant_dir)),
                            FieldCondition(
                                key="file",
                                match=MatchValue(value=str(artefact.repo_path)),
                            ),
                        ]
                    )
                ),
                payload={"obsolete": True},
            )
        except Exception as exc:
            logging.getLogger(__name__).warning("Vector cleanup failed: %s", exc)

    # persist vector before committing to git / graph
    if text_content:
        if should_embed(text_content):
            stored = False
            for attempt in range(1, VECTOR_STORE_RETRIES + 1):
                if vector_store.store_vector(
                    tenant_dir,
                    artefact.id,
                    text_content,
                    {"task": task_id, "file": artefact.repo_path, "sha": sha},
                ):
                    stored = True
                    break
                logging.warning("Vector store attempt %s failed", attempt)
                time.sleep(1)
            if not stored:
                raise RuntimeError("Vector store persistence failed")
        else:
            logging.info(
                "Skipping vector embedding for artifact due to irrelevance (content too short)."
            )

    action = "update" if original_exists and allow_overwrite else "add"
    _git_commit(artefact.repo_path, f"{task_id}: {action} artefact {artefact.sha256[:8]}")
    if original_exists and allow_overwrite:
        ARTIFACT_UPDATES.inc()
    try:
        _link_neo4j(task_id, sha)
    except Exception:
        # Fehler im Neo4j-Link wurden bereits geloggt
        pass
    logging.info(f"Registered artefact for Task {task_id}: {artefact.repo_path} (SHA256={sha[:8]})")
    return artefact


def retract_artifact(artifact_id: str, remove_from_neo4j: bool = False) -> None:
    """Remove an artifact's vector embedding from Qdrant and optionally from Neo4j."""
    # Delete all vector entries for the given artifact from the vector store
    if vector_store.client:
        try:
            # Remove points by artifact_id (all chunks) using Qdrant filter
            from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue

            vector_store.client.delete(
                collection_name=vector_store.collection_name,
                points_selector=FilterSelector(
                    filter=Filter(
                        must=[
                            FieldCondition(key="artifact_id", match=MatchValue(value=artifact_id))
                        ]
                    )
                ),
            )
        except Exception as exc:
            logging.getLogger(__name__).warning("Vector retraction via filter failed: %s", exc)
            try:
                # Fallback: direct deletion by ID (non-chunked entries)
                vector_store.client.delete(
                    collection_name=vector_store.collection_name,
                    points_selector=[artifact_id],
                )
            except Exception as exc2:
                logging.getLogger(__name__).warning("Vector retraction by ID failed: %s", exc2)
    if remove_from_neo4j:
        try:
            sha_val = None
            with Session(engine) as session:
                art_obj = session.get(Artifact, artifact_id)
                if art_obj:
                    sha_val = art_obj.sha256
            if sha_val:
                with driver.session() as g:
                    g.run("MATCH (a:Artifact {sha256:$sha}) DETACH DELETE a", sha=sha_val)
        except Exception as exc:
            logging.getLogger(__name__).warning("Neo4j artifact removal failed: %s", exc)


# Maintain backward compatibility
save_artefact = register_artefact
