"""LLM powered agent tasks."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Template

from llm import chat_completion
from celery import shared_task
from sqlmodel import Session

from ai_org_backend.db import engine
from ai_org_backend.models.task import Task
from ai_org_backend.main import Repo
from ai_org_backend.orchestrator.inspector import (
    insights_generated_total,
    alert,
)

PROMPT_DIR = (Path(__file__).resolve().parents[2].parent / "prompts").resolve()
TMPL_DEV = Template((PROMPT_DIR / "dev.j2").read_text(encoding="utf-8"))
TMPL_ANALYST = Template((PROMPT_DIR / "analyst.j2").read_text(encoding="utf-8"))


def render_dev(**ctx: str) -> str:
    """Return dev prompt rendered with context."""
    return TMPL_DEV.render(**ctx)


def generate_dev_code(**ctx: str) -> str:
    """Return code snippet from dev agent."""
    prompt = render_dev(**ctx)
    return chat_completion(prompt)


@shared_task(name="ai_org_backend.tasks.llm_tasks.insight_agent", queue="insight")
def insight_agent(tenant: str, task_id: str) -> None:
    """Analyze a task and store insights."""
    with Session(engine) as s:
        task = s.get(Task, task_id)
        if not task:
            return
    prompt = TMPL_ANALYST.render(purpose="analysis", task=task.description)

    import backoff
    import openai

    @backoff.on_exception(backoff.expo, openai.OpenAIError, max_tries=3)
    def _ask_llm(p: str):
        return openai.Completion.create(
            engine="o3",
            prompt=p,
            max_tokens=500,
            temperature=0,
        )

    try:
        resp = _ask_llm(prompt)
        text = resp["choices"][0]["text"]
        Repo(tenant).update(task_id, notes=text, owner="Insight")
        insights_generated_total.labels(tenant).inc()
    except Exception as e:  # pragma: no cover - network
        alert(str(e), "llm")

