"""LLM powered agent tasks."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Template

from llm import chat_completion

PROMPT_DIR = Path(__file__).resolve().parents[2] / "prompts"
TMPL_DEV = Template((PROMPT_DIR / "dev.j2").read_text(encoding="utf-8"))


def render_dev(**ctx: str) -> str:
    """Return dev prompt rendered with context."""
    return TMPL_DEV.render(**ctx)


def generate_dev_code(**ctx: str) -> str:
    """Return code snippet from dev agent."""
    prompt = render_dev(**ctx)
    return chat_completion(prompt)

