from __future__ import annotations

import uuid
import hashlib
from datetime import datetime as dt
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from sqlmodel import SQLModel, Field, Relationship

if TYPE_CHECKING:
    from .task import Task


class Artifact(SQLModel, table=True):
    """Binary or text output of a task stored on disk."""

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), 
        primary_key=True
    )

    task_id: str = Field(foreign_key="task.id", nullable=False)
    
    # FIXED: Simple relationship without List[]
    task: "Task" = Relationship(back_populates="artifacts")

    repo_path: str = Field(nullable=False)
    media_type: str = Field(nullable=False)
    size: int = Field(default=0, ge=0)
    sha256: str = Field(nullable=False, min_length=64, max_length=64)
    created_at: dt = Field(default_factory=dt.utcnow, nullable=False)

    @classmethod
    def create_from_file(
        cls,
        task_id: str,
        abs_path: Path,
        repo_root: Path = Path.cwd() / "workspace",
    ) -> "Artifact":
        if not abs_path.exists():
            raise FileNotFoundError(f"Source file not found: {abs_path}")
        
        repo_root.mkdir(exist_ok=True, parents=True)
        tgt = repo_root / abs_path.name
        
        counter = 1
        original_tgt = tgt
        while tgt.exists():
            stem = original_tgt.stem
            suffix = original_tgt.suffix
            tgt = repo_root / f"{stem}_{counter}{suffix}"
            counter += 1
        
        tgt.write_bytes(abs_path.read_bytes())
        sha = hashlib.sha256(tgt.read_bytes()).hexdigest()
        
        return cls(
            task_id=task_id,
            repo_path=str(tgt.relative_to(repo_root)),
            media_type=_guess_media_type(tgt),
            size=tgt.stat().st_size,
            sha256=sha,
        )


def _guess_media_type(p: Path) -> str:
    suffix_lower = p.suffix.lower()
    
    if suffix_lower in {".md", ".txt", ".rst"}:
        return "text/markdown"
    
    if suffix_lower in {".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".json"}:
        return "text/x-source"
    
    if suffix_lower in {".png", ".jpg", ".jpeg", ".gif", ".svg"}:
        return f"image/{suffix_lower.lstrip('.')}"
    
    return "application/octet-stream"
