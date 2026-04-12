from __future__ import annotations

import hashlib
import logging
import mimetypes
import os
import shutil
import subprocess  # nosec B404
import time
from datetime import datetime as dt
from pathlib import Path
from typing import Optional

from neo4j import GraphDatabase
from sqlmodel import Session

from ai_org_backend.db import engine
from ai_org_backend.metrics import prom_counter
from ai_org_backend.models import Artifact, Task
from ai_org_backend.settings import settings

from .vector_store import VectorStore

log = logging.getLogger(__name__)

# Workspace root from settings (unified)
WORKSPACE: Path = settings.workspace_dir.resolve()


# ──────────────────────────────────────────────────────────────────────
# S3-01 / S3-02: Artifact content validation
# ──────────────────────────────────────────────────────────────────────

class ArtifactValidationError(ValueError):
    """Raised when artifact content fails validation checks."""


# Minimum byte sizes per media-type prefix (S3-02)
_MIN_SIZE_BY_TYPE: dict[str, int] = {
    "text/markdown": 50,         # ~10 words minimum
    "text/x-markdown": 50,
    "text/x-source": 20,         # at least a function stub
    "text/plain": 20,
    "application/json": 2,       # at least "{}" or "[]"
    "image/": 100,               # trivially small images are invalid
}

# Error-indicator patterns that should never be stored as artifacts
_ERROR_PATTERNS = (
    "⚠️ Purpose not found",
    "ERROR:",
    "⚠️ Budget exhausted",
    "Internal Server Error",
)


def _validate_artifact_content(
    data: bytes | str,
    media_type: str | None,
    filename: str | None,
) -> None:
    """S3-01/S3-02: Validate artifact content before persisting.

    Raises ``ArtifactValidationError`` on failure.
    """
    # Determine raw bytes
    if isinstance(data, str):
        raw = data.encode("utf-8")
    elif isinstance(data, bytes):
        raw = data
    else:
        return  # Path-based source – validated after copy

    # S3-01: Reject empty content
    if not raw or len(raw.strip()) == 0:
        raise ArtifactValidationError(
            f"Artifact content is empty (filename={filename})"
        )

    # S3-01: Detect error messages stored as artifacts
    text_preview = raw[:500].decode("utf-8", errors="ignore")
    for pattern in _ERROR_PATTERNS:
        if text_preview.startswith(pattern):
            raise ArtifactValidationError(
                f"Artifact content starts with error indicator: {pattern!r}"
            )

    # S3-02: Minimum size by media type
    resolved_type = (media_type or "").lower()
    if not resolved_type and filename:
        import mimetypes as _mt
        resolved_type = (_mt.guess_type(filename)[0] or "").lower()

    for type_prefix, min_size in _MIN_SIZE_BY_TYPE.items():
        if resolved_type.startswith(type_prefix):
            if len(raw) < min_size:
                raise ArtifactValidationError(
                    f"Artifact too small: {len(raw)} bytes < {min_size} minimum "
                    f"for type {resolved_type} (filename={filename})"
                )
            break

    # S3-02: Type-specific checks for text content
    if resolved_type.startswith("text/") or resolved_type.startswith("application/json"):
        text = raw.decode("utf-8", errors="ignore").strip()

        # JSON artifacts must be valid JSON
        if resolved_type == "application/json":
            import json as _json
            try:
                _json.loads(text)
            except _json.JSONDecodeError as exc:
                raise ArtifactValidationError(
                    f"JSON artifact is not valid JSON: {exc}"
                ) from exc

        # Markdown artifacts should have at least some real content
        if resolved_type in ("text/markdown", "text/x-markdown"):
            word_count = len(text.split())
            if word_count < 5:
                raise ArtifactValidationError(
                    f"Markdown artifact has only {word_count} words "
                    f"(minimum 5, filename={filename})"
                )

# Git identity (author + committer), configurable via env
GIT_NAME = os.getenv("GIT_AUTHOR_NAME", os.getenv("GIT_COMMITTER_NAME", "ai-org-bot"))
GIT_EMAIL = os.getenv("GIT_AUTHOR_EMAIL", os.getenv("GIT_COMMITTER_EMAIL", "noreply@ai.org"))

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


def _ensure_repo(repo_dir: Path) -> None:
    """Initialise a Git repository if needed and configure identity."""
    repo_dir.mkdir(parents=True, exist_ok=True)
    if not (repo_dir / ".git").exists():
        subprocess.run(["git", "init", str(repo_dir)], check=True)  # nosec B603 B607
        subprocess.run(["git", "-C", str(repo_dir), "branch", "-M", "main"], check=False)  # nosec B603 B607
        (repo_dir / ".gitkeep").write_text("", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo_dir), "add", "-A"], check=True)  # nosec B603 B607
        subprocess.run(
            [
                "git",
                "-C",
                str(repo_dir),
                "-c",
                f"user.name={GIT_NAME}",
                "-c",
                f"user.email={GIT_EMAIL}",
                "commit",
                "-m",
                "init workspace",
                "--quiet",
            ],
            check=True,
        )  # nosec B603 B607
    subprocess.run(
        ["git", "config", "--global", "--add", "safe.directory", str(repo_dir)],
        check=False,
    )  # nosec B603 B607
    subprocess.run(
        ["git", "-C", str(repo_dir), "config", "user.name", GIT_NAME],
        check=False,
    )  # nosec B603 B607
    subprocess.run(
        ["git", "-C", str(repo_dir), "config", "user.email", GIT_EMAIL],
        check=False,
    )  # nosec B603 B607


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _mime(p: Path) -> str:
    mt, _ = mimetypes.guess_type(p)
    return mt or "application/octet-stream"


def _git_commit(rel_path: str, message: str) -> None:
    """Add & commit changes in the workspace repository."""
    _ensure_repo(WORKSPACE)
    # Entferne ggf. verwaiste Git-Lock-Datei
    lockfile = WORKSPACE / ".git" / "index.lock"
    if lockfile.exists():
        try:
            lockfile.unlink()
            log.info("Removed stale Git index.lock")
        except Exception as e:
            log.warning("Failed to remove Git index.lock: %s", e)
    try:
        subprocess.run(
            ["git", "-C", str(WORKSPACE), "add", "-A"],
            check=True,
            capture_output=True,
            text=True,
        )  # nosec B603 B607
    except subprocess.CalledProcessError as e:
        err_msg = getattr(e, "stderr", None) or str(e)
        if "index file smaller than expected" in err_msg.lower():
            idx_file = WORKSPACE / ".git" / "index"
            if idx_file.exists():
                try:
                    idx_file.unlink()
                    log.warning("Removed corrupt Git index")
                except Exception as ex:
                    log.error("Failed to remove corrupt index: %s", ex)
            subprocess.run(["git", "-C", str(WORKSPACE), "reset", "--mixed"], check=False)
            subprocess.run(
                ["git", "-C", str(WORKSPACE), "add", "-A"],
                check=True,
                capture_output=True,
                text=True,
            )
        else:
            raise
    status = subprocess.run(
        ["git", "-C", str(WORKSPACE), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
    )  # nosec B603 B607
    if not status.stdout.strip():
        log.info("storage: nothing to commit in %s", WORKSPACE)
        return
    commit_cmd = [
        "git",
        "-C",
        str(WORKSPACE),
        "-c",
        f"user.name={GIT_NAME}",
        "-c",
        f"user.email={GIT_EMAIL}",
        "commit",
        "-m",
        message,
        "--quiet",
    ]
    try:
        subprocess.run(
            commit_cmd,
            check=True,
            capture_output=True,
            text=True,
        )  # nosec B603 B607
    except subprocess.CalledProcessError as e:
        err_msg = getattr(e, "stderr", None) or str(e)
        if "index file smaller than expected" in err_msg.lower():
            idx_file = WORKSPACE / ".git" / "index"
            if idx_file.exists():
                try:
                    idx_file.unlink()
                    log.warning("Removed corrupt Git index before commit")
                except Exception as ex:
                    log.error("Failed to remove corrupt index: %s", ex)
            subprocess.run(["git", "-C", str(WORKSPACE), "reset", "--mixed"], check=False)
            subprocess.run(
                ["git", "-C", str(WORKSPACE), "add", "-A"],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                commit_cmd,
                check=True,
                capture_output=True,
                text=True,
            )
        else:
            raise


def resolve_for_read(repo_path: str) -> Path:
    """Resolve a repo_path to a safe absolute path under WORKSPACE."""
    candidate = Path(repo_path)
    if candidate.is_absolute():
        p = candidate.resolve()
        if str(p).startswith(str(WORKSPACE)):
            return p
        candidate = Path(candidate.as_posix().lstrip("/"))
    abs_path = (WORKSPACE / candidate).resolve()
    if not str(abs_path).startswith(str(WORKSPACE)):
        raise ValueError("repo_path escapes workspace root")
    return abs_path


def _link_neo4j(
    task_id: str,
    artefact_sha: str,
    *,
    status: Optional[str] = None,
    desc: Optional[str] = None,
) -> None:
    """Link artifact to task in Neo4j graph, ensuring both nodes and relation exist."""
    try:
        from ai_org_backend.services import graph_sync

        graph_sync.upsert_artifact(task_id, artefact_sha, status=status, desc=desc)
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
    src: Path | bytes | str,
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
    # S3-01/S3-02: Validate content before persisting
    if isinstance(src, (bytes, str)):
        try:
            _validate_artifact_content(src, media_type, filename)
        except ArtifactValidationError as exc:
            log.warning("Artifact validation failed for task %s: %s", task_id, exc)
            raise

    # Determine tenant workspace directory, optionally including purpose
    with Session(engine) as session:
        task_obj = session.get(Task, task_id)
        tenant_dir = task_obj.tenant_id if task_obj else "default"
        purpose_dir = task_obj.purpose_id if task_obj and task_obj.purpose_id else None
    target_dir = WORKSPACE / tenant_dir / purpose_dir if purpose_dir else WORKSPACE / tenant_dir
    target_dir.mkdir(exist_ok=True, parents=True)
    # Determine target file path and ensure unique name
    if isinstance(src, (bytes, str)):
        if not filename:
            raise ValueError("`filename` required when passing bytes or str.")
        base_name = filename
    else:
        src = Path(src).expanduser().resolve()
        base_name = filename or src.name
    base_name = (base_name or "artifact").strip().lstrip("/\\")
    if not Path(base_name).suffix and media_type in ("text/markdown", "text/x-markdown"):
        base_name = f"{base_name}.md"
    # Avoid duplicated tenant/purpose segments in nested filenames
    parts = Path(base_name).parts
    filtered_parts = [p for p in parts if p not in (tenant_dir, purpose_dir)]
    if filtered_parts:
        base_name = os.path.join(*filtered_parts)
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
    try:
        if isinstance(src, bytes):
            tgt.write_bytes(src)
        elif isinstance(src, str):
            tgt.write_text(src)
        else:
            shutil.copy2(src, tgt)
    except Exception as exc:  # pragma: no cover - defensive
        logging.error("Failed to write artifact to %s: %s", tgt, exc)
        raise

    # Compute metadata
    try:
        sha = _sha256(tgt)
    except Exception as exc:  # pragma: no cover - defensive
        logging.error("Failed to compute SHA256 for %s: %s", tgt, exc)
        raise

    # ── S1-10: Idempotency - check for duplicate artifact ──
    with Session(engine) as session:
        from sqlmodel import select
        existing = session.exec(
            select(Artifact).where(
                Artifact.task_id == task_id,
                Artifact.sha256 == sha,
            )
        ).first()
        if existing:
            log.warning(
                "Duplicate artifact detected for task %s (sha=%s). Returning existing artifact %s.",
                task_id, sha[:8], existing.id,
            )
            return existing

    # S3-12: Determine version number (auto-increment when task already has artifacts)
    version_number = 1
    parent_artifact_id = None
    with Session(engine) as session:
        from sqlmodel import select as _sel
        prev = session.exec(
            _sel(Artifact)
            .where(Artifact.task_id == task_id)
            .order_by(Artifact.created_at.desc())
        ).first()
        if prev:
            version_number = (prev.version_number or 1) + 1
            parent_artifact_id = prev.id

    artefact = Artifact(
        task_id=task_id,
        repo_path=str(tgt.relative_to(WORKSPACE)),
        media_type=media_type or _mime(tgt),
        size=tgt.stat().st_size,
        sha256=sha,
        version_number=version_number,
        parent_id=parent_artifact_id,
    )
    text_content: Optional[str] = None
    tokens = 0
    # Save artefact in database and link to task
    task_status: Optional[str] = None
    task_desc: Optional[str] = None
    try:
        with Session(engine) as session:
            session.add(artefact)
            task_obj = session.get(Task, task_id)
            if task_obj:
                task_status = str(task_obj.status) if task_obj.status is not None else None
                task_desc = task_obj.description or ""
                # Update token usage (approximate)
                try:
                    text_content = tgt.read_text(encoding="utf-8", errors="ignore")
                    word_count = len(text_content.split())
                except Exception as exc:  # pragma: no cover - defensive
                    logging.warning("Failed to read text content for %s: %s", tgt, exc)
                    text_content = None
                    word_count = 0
                tokens = int(word_count * 1.5)
                task_obj.tokens_actual += tokens
            session.commit()
            # Deduct budget for the tenant based on tokens used
            try:
                from ai_org_backend.services.budget import charge_tokens

                charge_tokens(task_obj.tenant_id, "", tokens)
            except Exception as e:
                logging.getLogger(__name__).error(
                    "Budget charge failed for tenant %s: %s", task_obj.tenant_id, e
                )
            session.refresh(artefact)
    except Exception as exc:  # pragma: no cover - defensive
        logging.error("Failed to register artifact in database: %s", exc)
        raise
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
                try:
                    success = vector_store.store_vector(
                        tenant_dir,
                        artefact.id,
                        text_content,
                        {"task": task_id, "file": artefact.repo_path, "sha": sha},
                    )
                except Exception as exc:
                    logging.warning("Vector store attempt %s raised exception: %s", attempt, exc)
                    time.sleep(1)
                    continue
                if success:
                    stored = True
                    break
                logging.warning("Vector store attempt %s failed", attempt)
                time.sleep(1)
            if not stored:
                logging.error(
                    "Vector store persistence failed after %s attempts", VECTOR_STORE_RETRIES
                )
                # Do not raise to avoid blocking artifact saving
        else:
            logging.info(
                "Skipping vector embedding for artifact due to irrelevance (content too short)."
            )

    action = "update" if original_exists and allow_overwrite else "add"
    try:
        _git_commit(artefact.repo_path, f"{task_id}: {action} artefact {artefact.sha256[:8]}")
    except Exception as e:  # pragma: no cover - defensive
        # Artefact wurde bereits gespeichert; Git-Fehler sollten den Request nicht brechen
        log.error("storage: git commit failed (continuing without crash): %s", e)
    if original_exists and allow_overwrite:
        ARTIFACT_UPDATES.inc()
    try:
        _link_neo4j(task_id, sha, status=task_status, desc=task_desc)
    except Exception:
        # Fehler im Neo4j-Link wurden bereits geloggt
        pass  # nosec
    # Mark the task as done
    try:
        with Session(engine) as session:
            t = session.get(Task, task_id)
            if t:
                t.status = "done"
                session.add(t)
                session.commit()
    except Exception as e:
        logging.getLogger(__name__).error(
            "Failed to update task status for Task %s: %s", task_id, e
        )
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
