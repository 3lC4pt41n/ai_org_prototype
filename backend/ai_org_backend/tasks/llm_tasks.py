"""LLM powered agent tasks."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Template

from ai_org_backend.utils.llm import chat_completion, chat
from celery import shared_task
from ai_org_backend.orchestrator.inspector import insights_generated_total

PROMPT_DIR = Path(__file__).resolve().parents[2] / "prompts"
TMPL_DEV = Template((PROMPT_DIR / "dev.j2").read_text(encoding="utf-8"))


def render_dev(**ctx: str) -> str:
    """Return dev prompt rendered with context."""
    return TMPL_DEV.render(**ctx)


def generate_dev_code(**ctx: str) -> str:
    """Return code snippet from dev agent."""
    prompt = render_dev(**ctx)
    return chat_completion(prompt)


@shared_task(name="ai_org_backend.tasks.llm_tasks.insight_agent", queue="insight")
def insight_agent(tenant: str, task_id: str) -> None:
    """Generate insights for a task via OpenAI and store artefact."""
    prompt_file = PROMPT_DIR / "analyst.j2"
    tmpl = Template(prompt_file.read_text(encoding="utf-8"))
    prompt = tmpl.render(purpose="demo", task=task_id)

    def _ask_llm(p: str):
        return chat(
            model="o3",
            messages=[{"role": "user", "content": p}],
            max_tokens=500,
            temperature=0,
        )

    try:
        response = _ask_llm(prompt)
        txt = response.choices[0].message.content
    except Exception as exc:
        txt = f"ERROR: {exc}"

    from ai_org_backend.services.storage import register_artefact
    register_artefact(task_id, txt.encode(), filename=f"{task_id}_insight.txt")
    from ai_org_backend.main import Repo
    Repo(tenant).update(task_id, status="done", owner="Insight", notes="analysis")
    insights_generated_total.inc()

