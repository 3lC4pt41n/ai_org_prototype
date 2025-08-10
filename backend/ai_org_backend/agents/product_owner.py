from __future__ import annotations

import time
from pathlib import Path

from ai_org_backend.metrics import prom_counter, prom_hist
from ai_org_backend.models import Purpose
from ai_org_backend.services.budget import BudgetExceededError
from ai_org_backend.services.llm_client import MODEL_PRO, chat_with_tools
from jinja2 import Template

PRODUCT_REQ_RUNS = prom_counter(
    "ai_product_requirements_runs_total", "Product Requirements agent executions"
)
PRODUCT_REQ_LATENCY = prom_hist(
    "ai_product_requirements_latency_seconds", "Product Requirements agent latency"
)

PROMPT_TMPL = Template(Path("prompts/requirements.j2").read_text(encoding="utf-8"))


def run_requirements(purpose: Purpose) -> str:
    """Generate a detailed Product Requirements Document (PRD) for the given project purpose."""

    ctx = {"purpose": purpose.name}
    prompt = PROMPT_TMPL.render(**ctx)
    start_time = time.time()
    try:
        resp = chat_with_tools(
            messages=[{"role": "user", "content": prompt}],
            model=MODEL_PRO,
            tenant_id=purpose.tenant_id,
            usage_label="requirements",
        )
        PRODUCT_REQ_RUNS.inc()
        content = resp["choices"][0]["message"]["content"]
        return content
    except BudgetExceededError:
        return "⚠️ Budget exhausted during requirements gathering. Please top up and retry."
    finally:
        PRODUCT_REQ_LATENCY.observe(time.time() - start_time)
