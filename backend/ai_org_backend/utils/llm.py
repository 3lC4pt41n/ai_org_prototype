"""Convenience wrappers around the unified LLM client.

Both ``chat()`` and ``chat_completion()`` automatically route to the correct
provider (OpenAI or Anthropic) based on the model name.

S2-09: Exponential backoff is configured with max 5 retries and a 5-minute
cap via the ``@backoff.on_exception`` decorator.
"""

import logging
import backoff  # S1-13: Required dependency - no fallback stub
import openai
from ai_org_backend.models.chat import ChatRole
from ai_org_backend.services import budget, llm_client
from ai_org_backend.services.llm_errors import MAX_BACKOFF_S


def _extract_tokens(resp) -> int:
    usage = getattr(resp, "usage", None)
    if isinstance(resp, dict):
        usage = resp.get("usage")
    if usage:
        if isinstance(usage, dict):
            return int(usage.get("total_tokens") or 0)
        total = getattr(usage, "total_tokens", None)
        if total is None and hasattr(usage, "to_dict"):
            total = usage.to_dict().get("total_tokens")
        if total is not None:
            try:
                return int(total)
            except (TypeError, ValueError):
                pass
    try:
        content = (
            resp["choices"][0]["message"].get("content")
            if isinstance(resp, dict)
            else resp.choices[0].message.content
        )
        return max(1, int(len(content) / 4))
    except Exception:
        return 0


# ── Retry-capable exceptions for both providers ──
_RETRYABLE: tuple = (openai.OpenAIError,)
try:
    import anthropic as _anthropic_mod

    _RETRYABLE = (openai.OpenAIError, _anthropic_mod.APIError)
except ImportError:
    pass


@backoff.on_exception(
    backoff.expo, _RETRYABLE, max_tries=5, max_time=MAX_BACKOFF_S, jitter=backoff.full_jitter
)
def chat(model: str, messages: list[dict], tenant_id: str | None = None, **kw):
    """Execute a chat completion.  Routes to OpenAI or Anthropic by model name."""

    if llm_client.is_anthropic_model(model):
        # Delegate fully to chat_with_tools which handles Anthropic routing,
        # format translation, budget and metrics.
        resp = llm_client.chat_with_tools(
            messages=messages,
            model=model,
            tenant_id=tenant_id,
            temperature=kw.pop("temperature", 0.2),
            max_output_tokens=kw.pop("max_tokens", kw.pop("max_output_tokens", None)),
            usage_label=kw.pop("usage_label", "chat"),
        )
        return resp  # already an OpenAI-shaped dict

    # OpenAI path (original behaviour)
    client = llm_client.ensure_client()
    resp = client.chat.completions.create(model=model, messages=messages, **kw)
    total_tokens = _extract_tokens(resp)
    if tenant_id and total_tokens > 0:
        try:
            budget.charge_tokens(tenant_id, model, total_tokens)
        except budget.BudgetExceededError:
            logging.warning("Tenant %s exceeded budget during chat", tenant_id)
    return resp


@backoff.on_exception(
    backoff.expo, _RETRYABLE, max_tries=5, max_time=MAX_BACKOFF_S, jitter=backoff.full_jitter
)
def chat_completion(
    prompt: str,
    model: str = "gpt-3.5-turbo",
    tenant_id: str | None = None,
    **kw,
) -> str:
    resp = chat(
        model=model,
        messages=[{"role": ChatRole.USER.value, "content": prompt}],
        tenant_id=tenant_id,
        **kw,
    )
    return (
        resp["choices"][0]["message"]["content"]
        if isinstance(resp, dict)
        else resp.choices[0].message.content
    )
