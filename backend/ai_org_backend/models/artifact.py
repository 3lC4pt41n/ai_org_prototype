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
    
    # SQLModel-Style Relationship statt SQLAlchemy
    task: "Task" = Relationship(
        back_populates="artifacts",
        sa_relationship_kwargs={"foreign_keys": "[Artifact.task_id]"}
    )

    repo_path: str = Field(nullable=False)
    media_type: str = Field(nullable=False)
    size: int = Field(default=0, ge=0)  # >= 0 validation
    sha256: str = Field(nullable=False, min_length=64, max_length=64)  # SHA256 ist immer 64 Zeichen
    created_at: dt = Field(default_factory=dt.utcnow, nullable=False)

    @classmethod
    def create_from_file(
        cls,
        task_id: str,
        abs_path: Path,
        repo_root: Path = Path.cwd() / "workspace",
    ) -> "Artifact":
        """Create artifact from file and copy to repository."""
        if not abs_path.exists():
            raise FileNotFoundError(f"Source file not found: {abs_path}")
        
        repo_root.mkdir(exist_ok=True, parents=True)
        tgt = repo_root / abs_path.name
        
        # Handle file name conflicts
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

    def get_full_path(self, repo_root: Path = Path.cwd() / "workspace") -> Path:
        """Get absolute path to the artifact file."""
        return repo_root / self.repo_path

    def read_content(self, repo_root: Path = Path.cwd() / "workspace") -> bytes:
        """Read artifact content from disk."""
        full_path = self.get_full_path(repo_root)
        if not full_path.exists():
            raise FileNotFoundError(f"Artifact file not found: {full_path}")
        return full_path.read_bytes()

    def verify_integrity(self, repo_root: Path = Path.cwd() / "workspace") -> bool:
        """Verify file integrity using SHA256 hash."""
        try:
            content = self.read_content(repo_root)
            current_hash = hashlib.sha256(content).hexdigest()
            return current_hash == self.sha256
        except FileNotFoundError:
            return False


def _guess_media_type(p: Path) -> str:
    """Guess media type based on file extension."""
    suffix_lower = p.suffix.lower()
    
    # Text files
    if suffix_lower in {".md", ".txt", ".rst"}:
        return "text/markdown"
    
    # Source code
    if suffix_lower in {".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".json", ".yaml", ".yml"}:
        return "text/x-source"
    
    # Images
    if suffix_lower in {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}:
        return f"image/{suffix_lower.lstrip('.')}"
    
    # Documents
    if suffix_lower in {".pdf", ".doc", ".docx"}:
        return f"application/{suffix_lower.lstrip('.')}"
    
    return "application/octet-stream"
