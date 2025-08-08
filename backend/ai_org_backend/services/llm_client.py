"""Unified OpenAI client wrapper.

Provides a simple helper around the official OpenAI SDK (>=1.40)
with model defaults taken from environment variables. The wrapper
also automatically enables reasoning for "thinking" models.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

import openai

from .billing import balance, charge

try:  # pragma: no cover - import guard for tests that stub openai
    _client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
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
    tenant: str | None = None,
) -> Dict[str, Any] | None:
    """Execute a ChatCompletion call with optional function-calling tools.

    If ``tenant`` is provided, the token usage of the call is converted into
    USD and deducted from the tenant's budget. When the remaining budget would
    fall below zero the response is discarded and ``None`` is returned.
    """
    use_model = model or MODEL_DEFAULT
    extra: Dict[str, Any] = {}
    if _is_thinking_model(use_model):
        extra["reasoning"] = {"effort": "medium"}

    if tenant is not None and balance(tenant) <= 0:
        logging.error("Tenant %s: budget exhausted. Declining LLM call.", tenant)
        return None

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
    except Exception as exc:  # pragma: no cover - defensive
        logging.exception("OpenAI chat completion failed: %s", exc)
        raise

    usage = data.get("usage", {})
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)
    cost_per_1k = float(os.getenv("USD_PER_1K_TOKENS", "0.0"))
    cost = (total_tokens / 1000.0) * cost_per_1k

    if tenant is not None:
        new_balance = charge(tenant, cost)
        if new_balance < 0:
            logging.error(
                "Tenant %s: Budget exhausted. Cost=$%.4f, balance=$%.4f. Declined.",
                tenant,
                cost,
                new_balance + cost,  # original balance before charge
            )
            return None
        logging.info(
            "Tenant %s | Model %s | Tokens: %s | Cost: $%.4f | Result: OK",
            tenant,
            use_model,
            total_tokens,
            cost,
        )
    else:
        logging.warning(
            "LLM call without tenant. Model %s, Tokens: %s, Cost: $%.4f",
            use_model,
            total_tokens,
            cost,
        )

    return data
