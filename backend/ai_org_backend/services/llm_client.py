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
) -> Dict[str, Any]:
    """Execute a ChatCompletion call with optional function-calling tools."""
    use_model = model or MODEL_DEFAULT
    extra: Dict[str, Any] = {}
    if _is_thinking_model(use_model):
        extra["reasoning"] = {"effort": "medium"}
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
        return resp.to_dict()
    except Exception as exc:  # pragma: no cover - defensive
        logging.exception("OpenAI chat completion failed: %s", exc)
        raise
