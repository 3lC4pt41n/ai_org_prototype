from __future__ import annotations

import json
import re
import time
from pathlib import Path

from jinja2 import Template
from ai_org_backend.utils.llm import chat
from ai_org_backend.metrics import prom_counter, prom_hist


PLANNER_RUNS = prom_counter("ai_planner_runs_total", "Planner executions")
PLANNER_LATENCY = prom_hist("ai_planner_latency_seconds", "Planner latency")
PROMPT_TMPL = Template(Path("prompts/planner.j2").read_text())


def run_planner(blueprint: str) -> list[dict]:
    """Generate a structured task plan (list of tasks with dependencies) from the blueprint."""
    ctx = {"task": blueprint}
    prompt = PROMPT_TMPL.render(**ctx)
    tasks: list[dict] = []
    model = "o3"
    for attempt in range(2):
        start = time.time()
        try:
            resp = chat(model=model, messages=[{"role": "user", "content": prompt}])
            PLANNER_RUNS.inc()
        finally:
            PLANNER_LATENCY.observe(time.time() - start)
        plan_text = resp.choices[0].message.content
        try:
            data = json.loads(plan_text)
        except Exception:
            data = None
        if data:
            if isinstance(data, dict) and "tasks" in data:
                tasks = data["tasks"]
            elif isinstance(data, list):
                tasks = data
        if tasks:
            break
        if attempt == 0:
            ctx["error_note"] = "previous output was not valid JSON"
            prompt = PROMPT_TMPL.render(**ctx)
            model = "o3-pro"
    return tasks

