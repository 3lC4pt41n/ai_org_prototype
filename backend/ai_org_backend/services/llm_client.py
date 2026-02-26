"""Unified LLM client wrapper supporting OpenAI *and* Anthropic models.

Model routing is transparent: callers pass a model name (e.g. ``"gpt-4o"``
or ``"claude-sonnet-4-20250514"``), and ``chat_with_tools()`` automatically
selects the right provider.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI

from . import budget
from .metrics_llm import LLM_CALLS, LLM_COST_USD, LLM_TOKENS, TENANT_BUDGET_LEFT

# ---------------------------------------------------------------------------
# Anthropic SDK – optional import (graceful degradation)
# ---------------------------------------------------------------------------
try:
    import anthropic as _anthropic_mod

    Anthropic = _anthropic_mod.Anthropic
    _HAS_ANTHROPIC = True
except ImportError:
    _anthropic_mod = None  # type: ignore[assignment]
    Anthropic = None  # type: ignore[assignment,misc]
    _HAS_ANTHROPIC = False
    logging.getLogger(__name__).info(
        "anthropic package not installed – Claude models will be unavailable."
    )

# ---------------------------------------------------------------------------
# Singletons
# ---------------------------------------------------------------------------
_openai_client: Optional[OpenAI] = None
_anthropic_client: Optional[Any] = None

# ---------------------------------------------------------------------------
# OpenAI key helpers
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Client initialisation
# ---------------------------------------------------------------------------

def ensure_client() -> OpenAI:
    """Initialise the OpenAI client once and return it."""

    global _openai_client
    if _openai_client is not None:
        return _openai_client

    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError(
            "OpenAI client not initialised. Please set OPENAI_API_KEY (or *_KEY/_APIKEY, "
            "or provide OPENAI_API_KEY_FILE / OPENAI_API_KEY_B64)."
        )

    logging.info("OpenAI key detected (mask=%s). Initialising client...", _mask(api_key))
    _openai_client = OpenAI(api_key=api_key)
    return _openai_client


def ensure_anthropic_client() -> Any:
    """Initialise the Anthropic client once and return it."""

    global _anthropic_client
    if _anthropic_client is not None:
        return _anthropic_client

    if not _HAS_ANTHROPIC:
        raise RuntimeError(
            "Anthropic SDK not installed. Run: pip install anthropic"
        )

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "Anthropic client not initialised. Please set ANTHROPIC_API_KEY."
        )

    logging.info("Anthropic key detected (mask=%s). Initialising client...", _mask(api_key))
    _anthropic_client = Anthropic(api_key=api_key)
    return _anthropic_client


# ---------------------------------------------------------------------------
# Model configuration
# ---------------------------------------------------------------------------
MODEL_DEFAULT = os.getenv("OPENAI_MODEL_DEFAULT", "gpt-4o-mini")
MODEL_PRO = os.getenv("OPENAI_MODEL_PRO", "gpt-4o")
MODEL_THINKING = os.getenv("OPENAI_MODEL_THINKING", "gpt-4o-mini")

# Anthropic model tiers (optional overrides)
ANTHROPIC_MODEL_DEFAULT = os.getenv("ANTHROPIC_MODEL_DEFAULT", "")
ANTHROPIC_MODEL_PRO = os.getenv("ANTHROPIC_MODEL_PRO", "")
ANTHROPIC_MODEL_THINKING = os.getenv("ANTHROPIC_MODEL_THINKING", "")

# Known Anthropic model prefixes
_ANTHROPIC_PREFIXES = ("claude-",)


def is_anthropic_model(model: str) -> bool:
    """Return True when *model* should be routed to the Anthropic API."""
    return any(model.startswith(prefix) for prefix in _ANTHROPIC_PREFIXES)


def _is_thinking_model(model: str) -> bool:
    return "thinking" in model or model.startswith("o3") or model.endswith("-think")


# ---------------------------------------------------------------------------
# Anthropic helpers – translate between OpenAI and Anthropic formats
# ---------------------------------------------------------------------------

def _openai_messages_to_anthropic(
    messages: List[Dict[str, Any]],
) -> tuple[str | None, List[Dict[str, Any]]]:
    """Split messages into a ``system`` string and an Anthropic ``messages`` list.

    Anthropic expects ``system`` to be a top-level parameter, not a message role.
    """
    system_parts: list[str] = []
    anthropic_messages: list[dict[str, Any]] = []

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if role == "system":
            if content:
                system_parts.append(content)
        else:
            # Anthropic uses "user" and "assistant" roles
            a_role = "assistant" if role == "assistant" else "user"
            anthropic_messages.append({"role": a_role, "content": content})

    system_text = "\n\n".join(system_parts) if system_parts else None
    return system_text, anthropic_messages


def _openai_tools_to_anthropic(
    tools: List[Dict[str, Any]] | None,
) -> list[dict[str, Any]] | None:
    """Convert OpenAI function-calling tool definitions to Anthropic format."""
    if not tools:
        return None

    anthropic_tools: list[dict[str, Any]] = []
    for tool in tools:
        if tool.get("type") != "function":
            continue
        func = tool.get("function", {})
        anthropic_tools.append({
            "name": func.get("name", "unknown"),
            "description": func.get("description", ""),
            "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
        })

    return anthropic_tools or None


def _anthropic_response_to_openai(response: Any, model: str) -> Dict[str, Any]:
    """Normalise an Anthropic Messages response into an OpenAI-shaped dict.

    This allows all downstream code to treat Anthropic and OpenAI responses
    identically.
    """
    # Extract text content
    content_text = ""
    tool_calls: list[dict[str, Any]] = []

    for block in getattr(response, "content", []):
        if getattr(block, "type", None) == "text":
            content_text += getattr(block, "text", "")
        elif getattr(block, "type", None) == "tool_use":
            import json as _json
            tool_calls.append({
                "id": getattr(block, "id", ""),
                "type": "function",
                "function": {
                    "name": getattr(block, "name", ""),
                    "arguments": _json.dumps(getattr(block, "input", {})),
                },
            })

    message: Dict[str, Any] = {
        "role": "assistant",
        "content": content_text or None,
    }
    if tool_calls:
        message["tool_calls"] = tool_calls

    # Usage – translate Anthropic usage to OpenAI shape
    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "input_tokens", 0) if usage else 0
    output_tokens = getattr(usage, "output_tokens", 0) if usage else 0

    return {
        "id": getattr(response, "id", ""),
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": getattr(response, "stop_reason", "stop") or "stop",
            }
        ],
        "usage": {
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
    }


# ---------------------------------------------------------------------------
# Anthropic chat implementation
# ---------------------------------------------------------------------------

def _chat_anthropic(
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]] | None = None,
    model: str = "claude-sonnet-4-20250514",
    temperature: float = 0.2,
    max_output_tokens: int | None = None,
) -> Dict[str, Any]:
    """Execute a chat completion call against the Anthropic API."""
    client = ensure_anthropic_client()

    system_text, anthropic_msgs = _openai_messages_to_anthropic(messages)
    anthropic_tools = _openai_tools_to_anthropic(tools)

    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": anthropic_msgs,
        "temperature": temperature,
        "max_tokens": max_output_tokens or 4096,
    }
    if system_text:
        kwargs["system"] = system_text
    if anthropic_tools:
        kwargs["tools"] = anthropic_tools

    resp = client.messages.create(**kwargs)
    return _anthropic_response_to_openai(resp, model)


# ---------------------------------------------------------------------------
# Public unified entry point
# ---------------------------------------------------------------------------

def chat_with_tools(
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]] | None = None,
    model: str | None = None,
    temperature: float = 0.2,
    max_output_tokens: int | None = None,
    tenant_id: str | None = None,
    usage_label: str = "generic",
) -> Dict[str, Any]:
    """Execute a ChatCompletion call with optional function-calling tools.

    Automatically routes to OpenAI or Anthropic based on the model name.
    """
    use_model = model or MODEL_DEFAULT

    # ── Budget gate ──
    if tenant_id and budget.get_left(tenant_id) <= 0.0:
        LLM_CALLS.labels(tenant_id, use_model, usage_label, "blocked").inc()
        raise budget.BudgetExceededError(f"Tenant {tenant_id} has no remaining budget.")

    try:
        # ── Route to the correct provider ──
        if is_anthropic_model(use_model):
            data = _chat_anthropic(
                messages=messages,
                tools=tools,
                model=use_model,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            )
        else:
            # OpenAI path (unchanged)
            extra: Dict[str, Any] = {}
            if _is_thinking_model(use_model):
                extra["reasoning"] = {"effort": "medium"}

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

        # ── Token accounting (common for both providers) ──
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
        logging.exception("LLM chat completion failed (%s): %s", use_model, exc)
        if tenant_id:
            LLM_CALLS.labels(tenant_id, use_model, usage_label, "error").inc()
        raise
