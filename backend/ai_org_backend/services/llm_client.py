"""Unified OpenAI client wrapper with budget tracking and metrics."""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

from openai import OpenAI

from . import budget
from .metrics_llm import LLM_CALLS, LLM_TOKENS, LLM_COST_USD, TENANT_BUDGET_LEFT

try:  # pragma: no cover - import guard for tests that stub OpenAI
    _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except Exception:  # pragma: no cover - during tests stub may lack OpenAI
    _client = None

MODEL_DEFAULT = os.getenv("OPENAI_MODEL_DEFAULT", "o3")
MODEL_PRO = os.getenv("OPENAI_MODEL_PRO", "o3-pro")
MODEL_THINKING = os.getenv("OPENAI_MODEL_THINKING", "o3")


def _is_thinking_model(model: str) -> bool:
    return "thinking" in model or model.startswith("o3") or model.endswith("-think")


def chat_with_tools(
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]] | None = None,
    model: str | None = None,
    temperature: float = 0.2,
    max_output_tokens: int | None = None,
    tenant_id: str | None = None,
    usage_label: str = "generic",
) -> Dict[str, Any]:
    """Execute a ChatCompletion call with optional function-calling tools."""
    use_model = model or MODEL_DEFAULT
    extra: Dict[str, Any] = {}
    if _is_thinking_model(use_model):
        extra["reasoning"] = {"effort": "medium"}

    if tenant_id:
        try:
            if budget.get_left(tenant_id) <= 0.0:
                LLM_CALLS.labels(tenant_id, use_model, usage_label, "blocked").inc()
                raise budget.BudgetExceededError(
                    f"Tenant {tenant_id} has no remaining budget."
                )
        except Exception:
            pass

    try:
        if _client is None:
            raise RuntimeError("OpenAI client not initialised")
        resp = _client.chat.completions.create(
            model=use_model,
            messages=messages,
            tools=tools or None,
            tool_choice="auto" if tools else None,
            temperature=temperature,
            **({"max_tokens": max_output_tokens} if max_output_tokens else {}),
            **extra,
        )
        data = resp.to_dict()

        total_tokens = 0
        estimation = "no"
        u = data.get("usage") or {}
        if isinstance(u, dict) and "total_tokens" in u:
            total_tokens = int(u.get("total_tokens") or 0)
        else:
            try:
                content = data["choices"][0]["message"].get("content") or ""
                total_tokens = max(1, int(len(content) / 4))
                estimation = "yes"
            except Exception:
                total_tokens = 0
                estimation = "yes"

        if tenant_id:
            LLM_CALLS.labels(tenant_id, use_model, usage_label, "ok").inc()
            LLM_TOKENS.labels(tenant_id, use_model, usage_label, estimation).inc(
                total_tokens
            )

        if tenant_id and total_tokens > 0:
            cost = budget.charge_tokens(tenant_id, use_model, total_tokens)
            LLM_COST_USD.labels(tenant_id, use_model, usage_label).inc(cost)
            try:
                TENANT_BUDGET_LEFT.labels(tenant_id).set(budget.get_left(tenant_id))
            except Exception:
                pass

        return data
    except Exception as exc:  # pragma: no cover - defensive
        logging.exception("OpenAI chat completion failed: %s", exc)
        if tenant_id:
            LLM_CALLS.labels(tenant_id, use_model, usage_label, "error").inc()
        raise
