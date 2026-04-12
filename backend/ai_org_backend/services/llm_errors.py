"""S2-08 / S2-09 / S2-12: Differentiated LLM error handling, backoff, and fallback chains.

Provides:

- ``ErrorCategory`` enum to classify HTTP errors (rate-limit, auth, server, etc.)
- ``classify_error()`` to map any exception to the right category
- ``should_retry()`` to decide whether a failed call should be retried
- ``get_fallback_model()`` to resolve the next model in a provider-specific chain
- ``backoff_wait()`` to compute exponential backoff delay with jitter
"""

from __future__ import annotations

import logging
import random
import time
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# S2-08: Error classification
# ──────────────────────────────────────────────────────────────────────

class ErrorCategory(str, Enum):
    """Broad error categories for LLM API responses."""

    RATE_LIMIT = "rate_limit"       # 429 – retry with backoff
    AUTH = "auth"                   # 401/403 – do NOT retry, surface immediately
    SERVER = "server"               # 500/502/503 – retry with backoff
    TIMEOUT = "timeout"             # Request timeout – retry once or twice
    CONTEXT_LENGTH = "context"      # Token limit exceeded – reduce prompt, no retry
    BUDGET = "budget"               # Internal budget exceeded – no retry
    UNKNOWN = "unknown"             # Unclassified – single retry at most


def _get_status_code(exc: BaseException) -> int | None:
    """Extract HTTP status code from various exception types."""
    # OpenAI SDK
    resp = getattr(exc, "response", None)
    if resp is not None:
        code = getattr(resp, "status_code", None)
        if code is not None:
            return int(code)

    # Anthropic SDK
    status = getattr(exc, "status_code", None)
    if status is not None:
        return int(status)

    # httpx.Response nested attribute
    if resp is not None and hasattr(resp, "status"):
        return int(resp.status)

    return None


def classify_error(exc: BaseException) -> ErrorCategory:
    """Map an LLM-related exception to a broad error category."""
    exc_name = type(exc).__name__.lower()

    # Budget errors (internal)
    if "budget" in exc_name:
        return ErrorCategory.BUDGET

    # Context-length / token-limit errors
    for kw in ("context_length", "maximum context", "token limit", "too many tokens"):
        if kw in str(exc).lower():
            return ErrorCategory.CONTEXT_LENGTH

    # Timeout errors
    for kw in ("timeout", "timed out", "deadline"):
        if kw in exc_name or kw in str(exc).lower():
            return ErrorCategory.TIMEOUT

    # HTTP status code based classification
    code = _get_status_code(exc)
    if code is not None:
        if code == 429:
            return ErrorCategory.RATE_LIMIT
        if code in (401, 403):
            return ErrorCategory.AUTH
        if code >= 500:
            return ErrorCategory.SERVER

    # Rate-limit heuristic (some SDKs use special exception classes)
    if "ratelimit" in exc_name or "rate_limit" in exc_name:
        return ErrorCategory.RATE_LIMIT

    # Auth heuristic
    if "auth" in exc_name or "permission" in exc_name:
        return ErrorCategory.AUTH

    return ErrorCategory.UNKNOWN


def should_retry(category: ErrorCategory) -> bool:
    """Return True if the error category warrants a retry."""
    return category in (
        ErrorCategory.RATE_LIMIT,
        ErrorCategory.SERVER,
        ErrorCategory.TIMEOUT,
        ErrorCategory.UNKNOWN,
    )


# ──────────────────────────────────────────────────────────────────────
# S2-09: Exponential backoff with jitter (max 5 retries, 5 min cap)
# ──────────────────────────────────────────────────────────────────────

MAX_RETRIES = 5
MAX_BACKOFF_S = 300  # 5 minutes
BASE_DELAY_S = 2.0


def backoff_wait(attempt: int) -> float:
    """Compute delay (seconds) for the given attempt (0-indexed).

    Uses exponential backoff with full jitter, capped at ``MAX_BACKOFF_S``.
    """
    exp_delay = BASE_DELAY_S * (2 ** attempt)
    capped = min(exp_delay, MAX_BACKOFF_S)
    return random.uniform(0, capped)


def retry_after_header(exc: BaseException) -> float | None:
    """Extract Retry-After header value from an exception, if present."""
    resp = getattr(exc, "response", None)
    if resp is None:
        return None

    headers = getattr(resp, "headers", {})
    if not headers:
        return None

    raw = headers.get("Retry-After") or headers.get("retry-after")
    if raw is None:
        return None

    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


# ──────────────────────────────────────────────────────────────────────
# S2-12: Fallback model chains per provider
# ──────────────────────────────────────────────────────────────────────

# Each chain lists models from most capable to cheapest.
# ``get_fallback_model(current)`` returns the next model in the chain.

OPENAI_CHAIN: list[str] = [
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-3.5-turbo",
]

ANTHROPIC_CHAIN: list[str] = [
    "claude-opus-4-20250514",
    "claude-sonnet-4-20250514",
    "claude-3-5-haiku-20241022",
]

# Build lookup: model → next model in chain
_FALLBACK_MAP: dict[str, str | None] = {}
for chain in (OPENAI_CHAIN, ANTHROPIC_CHAIN):
    for i, model in enumerate(chain):
        _FALLBACK_MAP[model] = chain[i + 1] if i + 1 < len(chain) else None


def get_fallback_model(current_model: str) -> str | None:
    """Return the next fallback model for *current_model*, or None if at end of chain.

    Also handles versioned model names by trying prefix matching.
    """
    # Exact match
    if current_model in _FALLBACK_MAP:
        return _FALLBACK_MAP[current_model]

    # Prefix match (e.g. "gpt-4o-2024-11-20" → matches "gpt-4o")
    for chain in (OPENAI_CHAIN, ANTHROPIC_CHAIN):
        for i, model in enumerate(chain):
            if current_model.startswith(model) or model.startswith(current_model):
                return chain[i + 1] if i + 1 < len(chain) else None

    return None


# ──────────────────────────────────────────────────────────────────────
# Unified resilient call wrapper
# ──────────────────────────────────────────────────────────────────────

def resilient_llm_call(
    call_fn,
    *,
    model: str,
    max_retries: int = MAX_RETRIES,
    allow_fallback: bool = True,
    **call_kwargs,
):
    """Execute an LLM call with retry, backoff, and model fallback.

    Parameters
    ----------
    call_fn : callable
        The actual LLM function to invoke.  Called as
        ``call_fn(model=model, **call_kwargs)``.
    model : str
        Starting model name.
    max_retries : int
        Maximum retry attempts per model in the chain.
    allow_fallback : bool
        If True, try the next model in the fallback chain on exhaustion.

    Returns the result of ``call_fn`` on success.
    Raises the last exception on total failure.
    """
    current_model = model
    last_exc: BaseException | None = None

    while current_model is not None:
        for attempt in range(max_retries):
            try:
                return call_fn(model=current_model, **call_kwargs)
            except Exception as exc:
                last_exc = exc
                category = classify_error(exc)

                logger.warning(
                    "LLM call failed (model=%s, attempt=%d/%d, category=%s): %s",
                    current_model, attempt + 1, max_retries, category.value, exc,
                )

                if not should_retry(category):
                    if allow_fallback and category in (ErrorCategory.CONTEXT_LENGTH,):
                        # Context-length: try smaller model immediately
                        break
                    raise

                # Respect Retry-After header if present
                server_wait = retry_after_header(exc)
                wait = server_wait if server_wait else backoff_wait(attempt)
                logger.info(
                    "Retrying in %.1fs (attempt %d/%d, model=%s)",
                    wait, attempt + 1, max_retries, current_model,
                )
                time.sleep(wait)

        # Exhausted retries for current model – try fallback
        if not allow_fallback:
            break

        next_model = get_fallback_model(current_model)
        if next_model:
            logger.warning(
                "Falling back from %s to %s after %d failed attempts",
                current_model, next_model, max_retries,
            )
            current_model = next_model
        else:
            break

    # All retries and fallbacks exhausted
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("resilient_llm_call: no call attempted")
