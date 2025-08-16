"""Utilities for agent modules."""

from __future__ import annotations

from pathlib import Path
from jinja2 import Template


_PROMPTS_DIR: Path | None = None


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


def load_template(name: str) -> Template:
    """Load a Jinja2 template from the shared ``prompts`` directory."""

    global _PROMPTS_DIR
    if _PROMPTS_DIR is None:
        _PROMPTS_DIR = _find_prompts_dir()
    tmpl_file = _PROMPTS_DIR / name
    if not tmpl_file.exists():
        raise FileNotFoundError(f"Template '{name}' not found in '{_PROMPTS_DIR}'")
    return Template(tmpl_file.read_text(encoding="utf-8"))

