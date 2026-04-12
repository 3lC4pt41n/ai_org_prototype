"""S5-A4: Repo Snapshot for Point-in-Time Consistency.

Before each Dev-Agent dispatch, creates an immutable snapshot of the
workspace containing file hashes, directory tree, and current schema
version.  Enables race-condition detection ("this file was modified by
a peer since you started").

Usage::

    from ai_org_backend.services.repo_snapshot import create_snapshot, get_snapshot
    snap = create_snapshot(tenant_id, purpose_id, task_id)
    # Later:
    old = get_snapshot(tenant_id, purpose_id, task_id)
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime as dt
from pathlib import Path
from typing import Optional

from ai_org_backend.settings import settings

logger = logging.getLogger(__name__)

WORKSPACE: Path = settings.workspace_dir.resolve()
SNAPSHOT_DIR_NAME = ".repo_snapshots"
# Max files to hash (safety limit for very large repos)
MAX_FILES = 5000


@dataclass
class FileEntry:
    """Single file in the snapshot."""
    path: str
    sha256: str
    size: int
    modified_at: float


@dataclass
class RepoSnapshot:
    """Immutable point-in-time snapshot of the workspace."""
    snapshot_id: str
    tenant_id: str
    purpose_id: str
    task_id: str
    created_at: str
    file_count: int = 0
    files: list[FileEntry] = field(default_factory=list)
    directory_tree: list[str] = field(default_factory=list)
    generation_time_ms: int = 0

    def get_file_hash(self, path: str) -> Optional[str]:
        """Look up the SHA256 of a file at snapshot time."""
        for f in self.files:
            if f.path == path:
                return f.sha256
        return None

    def changed_since(self, other: "RepoSnapshot") -> list[str]:
        """Return list of file paths that changed between two snapshots."""
        old_hashes = {f.path: f.sha256 for f in other.files}
        changed: list[str] = []
        for f in self.files:
            old_sha = old_hashes.get(f.path)
            if old_sha is None or old_sha != f.sha256:
                changed.append(f.path)
        # Also detect deletions
        new_paths = {f.path for f in self.files}
        for old_path in old_hashes:
            if old_path not in new_paths:
                changed.append(old_path)
        return changed

    def to_dict(self) -> dict:
        return asdict(self)

    def to_prompt_text(self) -> str:
        """Compact summary for agent prompt injection."""
        lines = [
            f"### Repo Snapshot ({self.file_count} files, taken at {self.created_at})",
        ]
        if self.directory_tree:
            lines.append("Directory structure:")
            for d in self.directory_tree[:30]:
                lines.append(f"  {d}")
            if len(self.directory_tree) > 30:
                lines.append(f"  ... ({len(self.directory_tree) - 30} more directories)")
        return "\n".join(lines)


def _sha256_file(path: Path) -> str:
    """Compute SHA256 of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _snapshot_dir(tenant_id: str) -> Path:
    """Return the snapshot storage directory for a tenant."""
    d = WORKSPACE / tenant_id / SNAPSHOT_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def create_snapshot(
    tenant_id: str,
    purpose_id: str,
    task_id: str,
) -> RepoSnapshot:
    """S5-A4: Create an immutable snapshot of the workspace.

    Scans all files in the tenant's workspace directory, computes
    SHA256 hashes, and persists the snapshot as a JSON file.

    Returns the snapshot object.  Generation target: < 2s for 1000 files.
    """
    start = time.time()
    workspace_dir = WORKSPACE / tenant_id
    if not workspace_dir.exists():
        workspace_dir.mkdir(parents=True, exist_ok=True)

    snapshot_id = f"{task_id}_{int(time.time())}"

    files: list[FileEntry] = []
    dirs: set[str] = set()
    count = 0

    for path in sorted(workspace_dir.rglob("*")):
        # Skip snapshot directory itself and hidden dirs
        rel = path.relative_to(workspace_dir)
        rel_str = str(rel)
        if SNAPSHOT_DIR_NAME in rel_str or rel_str.startswith(".git"):
            continue

        if path.is_dir():
            dirs.add(rel_str)
            continue

        if count >= MAX_FILES:
            break

        try:
            stat = path.stat()
            sha = _sha256_file(path)
            files.append(FileEntry(
                path=rel_str,
                sha256=sha,
                size=stat.st_size,
                modified_at=stat.st_mtime,
            ))
            count += 1
        except (PermissionError, OSError) as exc:
            logger.debug("[S5-A4] Skipping file %s: %s", path, exc)

    gen_time_ms = int((time.time() - start) * 1000)

    snapshot = RepoSnapshot(
        snapshot_id=snapshot_id,
        tenant_id=tenant_id,
        purpose_id=purpose_id,
        task_id=task_id,
        created_at=dt.utcnow().isoformat(),
        file_count=len(files),
        files=files,
        directory_tree=sorted(dirs),
        generation_time_ms=gen_time_ms,
    )

    # Persist to disk
    snap_path = _snapshot_dir(tenant_id) / f"{snapshot_id}.json"
    try:
        snap_path.write_text(
            json.dumps(snapshot.to_dict(), default=str),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.warning("[S5-A4] Failed to persist snapshot: %s", exc)

    logger.info(
        "[S5-A4] Snapshot %s created: %d files in %dms",
        snapshot_id,
        len(files),
        gen_time_ms,
    )
    return snapshot


def get_snapshot(
    tenant_id: str,
    purpose_id: str,
    task_id: str,
) -> Optional[RepoSnapshot]:
    """Load the most recent snapshot for a task."""
    snap_dir = _snapshot_dir(tenant_id)
    candidates = sorted(
        snap_dir.glob(f"{task_id}_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return None

    try:
        data = json.loads(candidates[0].read_text(encoding="utf-8"))
        files = [FileEntry(**f) for f in data.get("files", [])]
        snap = RepoSnapshot(
            snapshot_id=data["snapshot_id"],
            tenant_id=data["tenant_id"],
            purpose_id=data["purpose_id"],
            task_id=data["task_id"],
            created_at=data["created_at"],
            file_count=data.get("file_count", len(files)),
            files=files,
            directory_tree=data.get("directory_tree", []),
            generation_time_ms=data.get("generation_time_ms", 0),
        )
        return snap
    except Exception as exc:
        logger.warning("[S5-A4] Failed to load snapshot: %s", exc)
        return None
