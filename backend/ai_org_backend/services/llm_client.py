"""Unified OpenAI client wrapper with budget tracking and metrics."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI

from . import budget
from .metrics_llm import LLM_CALLS, LLM_COST_USD, LLM_TOKENS, TENANT_BUDGET_LEFT

_client: Optional[OpenAI] = None

_ENV_CANDIDATES = ("OPENAI_API_KEY", "OPENAI_KEY", "OPENAI_APIKEY")


def _mask(s: str) -> str:
    if not s:
        return "<empty>"
    if len(s) <= 10:
        return "***"
    return f"{s[:7]}...{s[-4:]}"


def _get_api_key() -> Optional[str]:
    # 1) direct env vars
    for name in _ENV_CANDIDATES:
        v = os.getenv(name)
        if v and v.strip():
            return v.strip()

    # 2) file-based secret (Docker secrets)
    key_file = os.getenv("OPENAI_API_KEY_FILE")
    if key_file:
        p = Path(key_file)
        if p.exists():
            try:
                content = p.read_text(encoding="utf-8").strip()
                if content:
                    return content
            except Exception as e:
                logging.warning("Could not read API key from file %s: %s", p, e)

    # 3) base64 variant (optional)
    b64 = os.getenv("OPENAI_API_KEY_B64")
    if b64:
        try:
            import base64
            decoded = base64.b64decode(b64).decode("utf-8").strip()
            if decoded:
                return decoded
        except Exception as e:
            logging.warning("Could not decode OPENAI_API_KEY_B64: %s", e)

    return None


def ensure_client() -> OpenAI:
    """Initialise the OpenAI client once and return it."""

    global _client
    if _client is not None:
        return _client

    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError(
            "OpenAI client not initialised. Please set OPENAI_API_KEY (or *_KEY/_APIKEY, "
            "or provide OPENAI_API_KEY_FILE / OPENAI_API_KEY_B64)."
        )

    logging.info("OpenAI key detected (mask=%s). Initialising client...", _mask(api_key))
    _client = OpenAI(api_key=api_key)
    return _client


MODEL_DEFAULT = os.getenv("OPENAI_MODEL_DEFAULT", "gpt-4o-mini")
MODEL_PRO = os.getenv("OPENAI_MODEL_PRO", "gpt-4o")
MODEL_THINKING = os.getenv("OPENAI_MODEL_THINKING", "gpt-4o-mini")


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

    if tenant_id and budget.get_left(tenant_id) <= 0.0:
        LLM_CALLS.labels(tenant_id, use_model, usage_label, "blocked").inc()
        raise budget.BudgetExceededError(f"Tenant {tenant_id} has no remaining budget.")

    try:
        client = ensure_client()
        resp = client.chat.completions.create(
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
            LLM_TOKENS.labels(tenant_id, use_model, usage_label, estimation).inc(total_tokens)

        if tenant_id and total_tokens > 0:
            cost = budget.charge_tokens(tenant_id, use_model, total_tokens)
            LLM_COST_USD.labels(tenant_id, use_model, usage_label).inc(cost)
            try:
                TENANT_BUDGET_LEFT.labels(tenant_id).set(budget.get_left(tenant_id))
            except Exception as e:
                logging.error(
                    "Failed to update TENANT_BUDGET_LEFT for tenant %s: %s", tenant_id, e
                )

        return data
    except Exception as exc:  # pragma: no cover - defensive
        logging.exception("OpenAI chat completion failed: %s", exc)
        if tenant_id:
            LLM_CALLS.labels(tenant_id, use_model, usage_label, "error").inc()
        raise
