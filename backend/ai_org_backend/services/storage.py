from __future__ import annotations

import hashlib
import mimetypes
from datetime import datetime as dt
import os
import logging
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

from neo4j import GraphDatabase
from sqlmodel import Session

from ai_org_backend.db import engine
from ai_org_backend.models import Artifact, Task
from ai_org_backend.metrics import prom_counter
from .vector_store import VectorStore

WORKSPACE = Path.cwd() / "workspace"
WORKSPACE.mkdir(exist_ok=True)

NEO4J_URL = os.getenv("NEO4J_URL", "bolt://localhost:7687")
driver = GraphDatabase.driver(
    NEO4J_URL,
    auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASS", "s3cr3tP@ss")),
)

vector_store = VectorStore()
ARTIFACT_UPDATES = prom_counter(
    "ai_artifact_updates_total", "Count of artefacts overwritten via register_artefact"
)

# retry settings for vector persistence
VECTOR_STORE_RETRIES = 3

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
) -> Artifact:
    """Save artefact file for a completed task and register it in the database.
    If ``allow_overwrite`` is True and a file with the same name already exists in the
    tenant workspace, the existing file is replaced instead of creating a suffixed copy.
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
        media_type=_mime(tgt),
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
            from qdrant_client.models import Filter, FieldCondition, MatchValue, FilterSelector

            vector_store.client.delete(
                collection_name=vector_store.collection_name,
                points_selector=FilterSelector(
                    filter=Filter(
                        must=[
                            FieldCondition(key="tenant", match=MatchValue(value=tenant_dir)),
                            FieldCondition(key="file", match=MatchValue(value=str(artefact.repo_path))),
                        ]
                    )
                ),
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
                    {"task": task_id, "file": artefact.repo_path},
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
    _link_neo4j(task_id, sha)
    logging.info(
        f"Registered artefact for Task {task_id}: {artefact.repo_path} (SHA256={sha[:8]})"
    )
    return artefact


def retract_artifact(artifact_id: str, remove_from_neo4j: bool = False) -> None:
    """Remove an artifact's vector embedding from Qdrant and optionally from Neo4j."""
    # Delete all vector entries for the given artifact from the vector store
    if vector_store.client:
        try:
            # Remove points by artifact_id (all chunks) using Qdrant filter
            from qdrant_client.models import Filter, FieldCondition, MatchValue, FilterSelector

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
                logging.getLogger(__name__).warning(
                    "Vector retraction by ID failed: %s", exc2
                )
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
