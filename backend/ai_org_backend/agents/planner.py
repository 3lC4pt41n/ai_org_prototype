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
    prompt = PROMPT_TMPL.render(task=blueprint)
    start = time.time()
    try:
        resp = chat(model="o3", messages=[{"role": "user", "content": prompt}])
        PLANNER_RUNS.inc()
    finally:
        PLANNER_LATENCY.observe(time.time() - start)
    plan_text = resp.choices[0].message.content
    tasks = []
    # Try to extract JSON tasks if present
    md_json_rx = re.compile(r"```json([\s\S]+?)```", re.I)
    m = md_json_rx.search(plan_text)
    if m:
        try:
            data = json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            data = None
        if data:
            if isinstance(data, dict) and "tasks" in data:
                tasks = data["tasks"]
            elif isinstance(data, list):
                tasks = data
    if not tasks:
        # Try to find a JSON array in text
        try:
            lo = plan_text.index("[")
            hi = plan_text.rindex("]")
            data = json.loads(plan_text[lo:hi+1])
            if isinstance(data, list):
                tasks = data
            elif isinstance(data, dict) and "tasks" in data:
                tasks = data["tasks"]
        except Exception:
            data = None
        # Fallback to Markdown table parsing
        if not tasks:
            rows = [ln for ln in plan_text.splitlines() if ln.lstrip().startswith("|")]
            if len(rows) > 2:
                for r in rows[2:]:
                    cols = [c.strip() for c in r.strip("|").split("|")]
                    if len(cols) < 2:
                        continue
                    task_desc = cols[0]
                    depends = cols[1] if cols[1] not in {"-", ""} else None
                    slug = re.sub(r"\s+", "_", task_desc.lower())[:8] or f"task{len(tasks)+1}"
                    tasks.append({
                        "id": slug,
                        "description": task_desc,
                        "depends_on": depends,
                        "business_value": 1.0,
                        "tokens_plan": 1000,
                        "purpose_relevance": 0.5
                    })
    return tasks

