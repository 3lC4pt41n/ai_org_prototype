import logging

try:
    import backoff as _backoff
except Exception:  # pragma: no cover

    class _BackoffStub:
        """Minimaler Fallback, falls 'backoff' nicht installiert ist.
        Dekoratoren sind No-ops, damit die App trotzdem startet."""

        @staticmethod
        def expo(*args, **kwargs):
            def _passthrough(fn):
                return fn

            return _passthrough

        @staticmethod
        def on_exception(*args, **kwargs):
            def _decorator(fn):
                return fn

            return _decorator

    _backoff = _BackoffStub()
    logging.getLogger(__name__).warning("Package 'backoff' not installed; retry logic is disabled.")

backoff = _backoff
import openai
from ai_org_backend.services import budget


def _extract_tokens(resp) -> int:
    usage = getattr(resp, "usage", None)
    if isinstance(resp, dict):
        usage = resp.get("usage")
    if usage and isinstance(usage, dict):
        return int(usage.get("total_tokens") or 0)
    try:
        content = (
            resp["choices"][0]["message"].get("content")
            if isinstance(resp, dict)
            else resp.choices[0].message.content
        )
        return max(1, int(len(content) / 4))
    except Exception:
        return 0


@backoff.on_exception(backoff.expo, openai.OpenAIError, max_tries=3)
def chat(model: str, messages: list[dict], tenant_id: str | None = None, **kw):
    resp = openai.ChatCompletion.create(model=model, messages=messages, **kw)
    total_tokens = _extract_tokens(resp)
    if tenant_id and total_tokens > 0:
        try:
            budget.charge_tokens(tenant_id, model, total_tokens)
        except budget.BudgetExceededError:
            logging.warning("Tenant %s exceeded budget during chat", tenant_id)
    return resp


@backoff.on_exception(backoff.expo, openai.OpenAIError, max_tries=3)
def chat_completion(
    prompt: str,
    model: str = "gpt-3.5-turbo",
    tenant_id: str | None = None,
    **kw,
) -> str:
    resp = chat(
        model=model, messages=[{"role": "user", "content": prompt}], tenant_id=tenant_id, **kw
    )
    return (
        resp["choices"][0]["message"]["content"]
        if isinstance(resp, dict)
        else resp.choices[0].message.content
    )
