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
    logging.getLogger(__name__).warning(
        "Package 'backoff' not installed; retry logic is disabled."
    )

backoff = _backoff
import openai

@backoff.on_exception(backoff.expo, openai.OpenAIError, max_tries=3)
def chat(model: str, messages: list[dict], **kw):
    return openai.ChatCompletion.create(model=model, messages=messages, **kw)

@backoff.on_exception(backoff.expo, openai.OpenAIError, max_tries=3)
def chat_completion(prompt: str, model: str = "gpt-3.5-turbo", **kw) -> str:
    resp = openai.ChatCompletion.create(model=model, messages=[{"role": "user", "content": prompt}], **kw)
    return resp.choices[0].message.content
