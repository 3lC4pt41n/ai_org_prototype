from __future__ import annotations

import uuid
import hashlib
from datetime import datetime as dt
from pathlib import Path
from typing import TYPE_CHECKING
from sqlalchemy.orm import Mapped

from sqlmodel import SQLModel, Field, Relationship

if TYPE_CHECKING:
    from .task import Task


class Artifact(SQLModel, table=True):
    """Binary or text output of a task stored on disk."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)

    task_id: str = Field(foreign_key="task.id")
    task: Mapped["Task"] = Relationship(back_populates="artefacts")

    repo_path: str
    media_type: str
    size: int = 0
    sha256: str
    created_at: dt = Field(default_factory=dt.utcnow)

    @classmethod
    def create_from_file(
        cls,
        task_id: str,
        abs_path: Path,
        repo_root: Path = Path.cwd() / "workspace",
    ) -> "Artifact":
        repo_root.mkdir(exist_ok=True, parents=True)
        tgt = repo_root / abs_path.name
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
    if p.suffix in {".md", ".txt"}:
        return "text/markdown"
    if p.suffix in {".py", ".js", ".tsx"}:
        return "text/x-source"
    if p.suffix in {".png", ".jpg", ".jpeg"}:
        return "image/" + p.suffix.lstrip(".")
    return "application/octet-stream"
