from __future__ import annotations

import json
import logging
import re
import time

from jsonschema import validate

from ai_org_backend.metrics import prom_counter, prom_hist
from ai_org_backend.models.chat import ChatRole
from ai_org_backend.utils.llm import chat

from .utils import load_template

PLANNER_RUNS = prom_counter("ai_planner_runs_total", "Planner executions")
PLANNER_LATENCY = prom_hist("ai_planner_latency_seconds", "Planner latency")
PROMPT_TMPL = load_template("planner.j2")

# Maximum allowed retries for invalid LLM output (total 3 attempts)
MAX_AGENT_RETRIES = 2

# Expected schema for a task list
TASKS_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "description": {"type": "string"},
            "depends_on": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "business_value": {"type": "number"},
            "tokens_plan": {"type": "integer"},
            "purpose_relevance": {"type": "number"},
        },
        "required": [
            "id",
            "description",
            "depends_on",
            "business_value",
            "tokens_plan",
            "purpose_relevance",
        ],
    },
}

# Regex to extract JSON from Markdown code blocks
MD_JSON_RX = re.compile(r"```json([\s\S]+?)```", re.IGNORECASE)


def run_planner(blueprint: str) -> list[dict]:
    """Generate a structured task plan (list of tasks with dependencies) from the blueprint."""
    ctx = {"task": blueprint}
    prompt = PROMPT_TMPL.render(**ctx)
    tasks: list[dict] = []
    model = "o3"
    for attempt in range(MAX_AGENT_RETRIES + 1):
        start = time.time()
        try:
            resp = chat(model=model, messages=[{"role": ChatRole.USER.value, "content": prompt}])
            PLANNER_RUNS.inc()
        finally:
            PLANNER_LATENCY.observe(time.time() - start)
        plan_text = resp.choices[0].message.content

        data = None
        try:
            # 1) Direktes JSON-Parsing
            data = json.loads(plan_text)
        except json.JSONDecodeError:
            # 2) Fallback: JSON aus Markdown-Codeblock extrahieren
            m = MD_JSON_RX.search(plan_text)
            if m:
                try:
                    data = json.loads(m.group(1))
                except Exception:
                    data = None
            # 3) Weiterer Fallback: zwischen erstem '[' und letztem ']'
            if data is None:
                try:
                    lo = plan_text.index("[")
                    hi = plan_text.rindex("]")
                    snippet = plan_text[lo : hi + 1]
                    data = json.loads(snippet)
                except Exception:
                    data = None

        tasks_data = None
        if data:
            if isinstance(data, dict) and "tasks" in data:
                tasks_data = data["tasks"]
            elif isinstance(data, list):
                tasks_data = data
            # Schema validieren
            try:
                if tasks_data is not None:
                    validate(instance=tasks_data, schema=TASKS_SCHEMA)
                else:
                    raise ValueError("Schema validation skipped due to missing tasks list")
            except Exception:
                tasks_data = None

        if tasks_data:
            tasks = tasks_data
            break

        # No valid result -> prepare next attempt
        if attempt < MAX_AGENT_RETRIES:
            note_msg = (
                "previous output was not valid JSON"
                if data is None
                else "previous output did not follow the expected JSON format"
            )
            ctx["error_note"] = note_msg
            prompt = PROMPT_TMPL.render(**ctx)
            model = "o3-pro"
            logging.warning(
                "[Planner] invalid LLM output (attempt %s/%s): %s",
                attempt + 1,
                MAX_AGENT_RETRIES + 1,
                note_msg,
            )
        else:
            logging.error(f"[Planner] no valid task list after {attempt + 1} attempts")

    return tasks
