# models.py – DB schema for tasks + file artefacts  (SQLModel ≥ 0.0.14)
# ---------------------------------------------------------------------
from __future__ import annotations

import uuid, hashlib, os
from datetime import datetime as dt
from pathlib import Path
from typing import Optional

from sqlmodel import Field, SQLModel, create_engine, Session, select, Relationship


# ─────────────────────────── DB ENGINE ────────────────────────────
# DB_URL is read by ai_org_prototype.py, but keeping it here avoids
# circular imports when running Alembic / standalone scripts.
DB_URL = os.getenv("DATABASE_URL", "sqlite:///ai_org.db")
engine = create_engine(DB_URL, echo=False)


# ───────────────────────────  MODELS  ─────────────────────────────
class Tenant(SQLModel, table=True):
    """
    Simple tenant model (multi-tenant future-proofing).
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    name: str
    balance: float = 0.0

    # back‐refs
    tasks: list["Task"] = Relationship(back_populates="tenant")


class Task(SQLModel, table=True):
    """
    Core work item tracked in Neo4j + SQL.  One row per task-node.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8], primary_key=True)

    # FK
    tenant_id: str = Field(foreign_key="tenant.id")
    tenant: Optional[Tenant] = Relationship(back_populates="tasks")

    # Business fields
    description: str
    business_value: float = 1.0          # “bang for buck”, 0-10
    tokens_plan: int = 0                 # rough LLM budget (est.)
    tokens_actual: int = 0               # will be filled by orchestrator
    purpose_relevance: float = 0.0       # 0-100 %
    status: str = "todo"                 # todo | doing | done | failed
    owner: Optional[str] = None          # Dev / QA / UX …
    notes: str = ""

    # Dependencies – point to *another* sql row (mirrors Neo4j edge)
    depends_on: Optional[str] = Field(
        default=None,
        foreign_key="task.id",
        description="predecessor task id"
    )

    created_at: dt = Field(default_factory=dt.utcnow)

    # back‐refs
    artefacts: list["Artifact"] = Relationship(back_populates="task")


class Artifact(SQLModel, table=True):
    """
    Binary / text output of a task – source file, diagram, compiled asset, …
    Stored on disk (repo_path) & indexed here.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)

    # FK
    task_id: str = Field(foreign_key="task.id")
    task: Task = Relationship(back_populates="artefacts")

    # File meta
    repo_path: str                      # relative path in ./workspace/
    media_type: str                     # “text/markdown”, “image/png”, …
    size: int = 0                       # bytes
    sha256: str                         # integrity / dedup
    created_at: dt = Field(default_factory=dt.utcnow)

    @classmethod
    def create_from_file(
        cls,
        task_id: str,
        abs_path: Path,
        repo_root: Path = Path.cwd() / "workspace",
    ) -> "Artifact":
        """
        Helper: copy a file into the workspace repo and emit an Artifact row.
        """
        repo_root.mkdir(exist_ok=True, parents=True)
        tgt = repo_root / abs_path.name
        tgt.write_bytes(abs_path.read_bytes())          # naive copy

        sha = hashlib.sha256(tgt.read_bytes()).hexdigest()
        return cls(
            task_id=task_id,
            repo_path=str(tgt.relative_to(repo_root)),
            media_type=_guess_media_type(tgt),
            size=tgt.stat().st_size,
            sha256=sha,
        )


# ────────────────────  HELPER: guess MIME  ─────────────────────────
def _guess_media_type(p: Path) -> str:
    if p.suffix in {".md", ".txt"}:
        return "text/markdown"
    if p.suffix in {".py", ".js", ".tsx"}:
        return "text/x-source"
    if p.suffix in {".png", ".jpg", ".jpeg"}:
        return "image/" + p.suffix.lstrip(".")
    return "application/octet-stream"


# ───────────────────────────  INIT  ────────────────────────────────
def init_db() -> None:
    """
    Call once on startup (or via Alembic migrations in prod).
    """
    SQLModel.metadata.create_all(engine)


# CLI helper – ‘python models.py’ bootstraps an empty DB quickly
if __name__ == "__main__":
    init_db()
    print("✅  DB schema (tasks + artefacts) created.")
