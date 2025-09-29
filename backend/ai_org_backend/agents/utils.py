"""Utilities for agent modules."""

from __future__ import annotations

import os
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, Template
from sqlmodel import select

from ai_org_backend.db import SessionLocal
from ai_org_backend.models import PromptTemplate


_PROMPTS_DIR: Path | None = None
_ENV: Environment | None = None


def _find_prompts_dir() -> Path:
    """Locate the repository's ``prompts`` directory.

    Starting from this file's location we walk up the directory tree until a
    ``prompts`` folder is found. The search works both in the development
    environment (where the repository root contains ``prompts``) and inside the
    Docker image (where it is copied to ``/app/prompts``).
    """

    base = Path(__file__).resolve()
    for parent in [base, *base.parents]:
        candidate = parent / "prompts"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError("Could not locate 'prompts' directory")


def _get_prompts_dir() -> Path:
    """Return the directory containing prompt templates."""

    global _PROMPTS_DIR
    if _PROMPTS_DIR is not None:
        return _PROMPTS_DIR

    configured = Path(os.environ.get("PROMPTS_DIR", "/app/prompts"))
    if configured.exists():
        _PROMPTS_DIR = configured
        return _PROMPTS_DIR

    _PROMPTS_DIR = _find_prompts_dir()
    return _PROMPTS_DIR


def _get_environment() -> Environment:
    """Create (or reuse) a Jinja2 environment configured for prompt loading."""

    global _ENV
    if _ENV is None:
        prompts_dir = _get_prompts_dir()
        _ENV = Environment(
            loader=FileSystemLoader(str(prompts_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
        )
    return _ENV


def _db_prompt_is_valid(content: str | None) -> bool:
    """Return ``True`` if the DB-stored template content is usable."""

    if not content:
        return False
    stripped = content.strip()
    if not stripped:
        return False
    return "tbd" not in stripped.casefold()


def load_template(name: str) -> Template:
    """Load a Jinja2 template from the shared ``prompts`` directory."""

    env = _get_environment()

    try:
        with SessionLocal() as session:
            template = session.get(PromptTemplate, name)
            if template and _db_prompt_is_valid(template.content):
                return env.from_string(template.content)  # type: ignore[arg-type]

            if name.endswith(".j2"):
                template = session.exec(
                    select(PromptTemplate)
                    .where(PromptTemplate.default_path == name)
                    .order_by(PromptTemplate.created_at.desc())
                ).first()
                if template and _db_prompt_is_valid(template.content):
                    return env.from_string(template.content)  # type: ignore[arg-type]
    except Exception:
        # DB lookup is best-effort; fall back to filesystem prompts
        pass

    return env.get_template(name)

