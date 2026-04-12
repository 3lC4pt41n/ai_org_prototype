"""S2-10 / S2-11: Token counting and budget reservation.

Provides:

- ``count_tokens()`` – precise token counting via tiktoken (OpenAI) with
  a fast character-based fallback for Anthropic models or when tiktoken
  is unavailable.
- ``estimate_cost()`` – USD cost estimate for a given token count.
- ``reserve_budget()`` / ``release_reservation()`` – pre-call budget
  reservation to prevent over-spending when multiple calls run in parallel.

The reservation system uses Redis DECR/INCR for atomicity.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from . import budget

logger = logging.getLogger(__name__)

# ── tiktoken import (optional) ──
try:
    import tiktoken
    _HAS_TIKTOKEN = True
except ImportError:
    tiktoken = None  # type: ignore[assignment]
    _HAS_TIKTOKEN = False
    logger.info("tiktoken not installed – using character-based token estimation")

# ── Cache for tiktoken encodings ──
_encoding_cache: dict[str, Any] = {}


def _get_encoding(model: str) -> Any | None:
    """Return a tiktoken encoding for the model, or None if unavailable."""
    if not _HAS_TIKTOKEN:
        return None

    if model in _encoding_cache:
        return _encoding_cache[model]

    try:
        enc = tiktoken.encoding_for_model(model)
        _encoding_cache[model] = enc
        return enc
    except (KeyError, Exception):
        # Model not recognized by tiktoken – try cl100k_base as fallback
        try:
            enc = tiktoken.get_encoding("cl100k_base")
            _encoding_cache[model] = enc
            return enc
        except Exception:
            _encoding_cache[model] = None
            return None


# ──────────────────────────────────────────────────────────────────────
# S2-11: Precise token counting
# ──────────────────────────────────────────────────────────────────────

def count_tokens(text: str, model: str = "gpt-4o") -> int:
    """Count tokens for *text* using tiktoken if available, else estimate.

    For Anthropic models, we always use the character-based estimate
    (Anthropic does not publish a tiktoken-compatible tokenizer).
    """
    if not text:
        return 0

    # Anthropic models: use character estimate (≈4 chars/token)
    if model.startswith("claude-"):
        return max(1, len(text) // 4)

    enc = _get_encoding(model)
    if enc is not None:
        try:
            return len(enc.encode(text))
        except Exception:
            pass

    # Fallback: character-based estimate
    return max(1, len(text) // 4)


def count_messages_tokens(
    messages: List[Dict[str, Any]], model: str = "gpt-4o"
) -> int:
    """Count tokens across a list of chat messages.

    Accounts for the per-message overhead (role tokens, separators).
    """
    total = 0
    per_message_overhead = 4  # every message has <|start|>role content<|end|>

    for msg in messages:
        total += per_message_overhead
        content = msg.get("content", "")
        if isinstance(content, str):
            total += count_tokens(content, model)
        elif isinstance(content, list):
            # Multi-part content (images, text blocks)
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    total += count_tokens(part.get("text", ""), model)
                elif isinstance(part, dict) and part.get("type") == "image_url":
                    total += 85  # base cost for image token estimation

    total += 3  # assistant reply priming
    return total


def estimate_cost(tokens: int, model: str) -> float:
    """Estimate the USD cost for a given number of tokens."""
    price = budget.get_price_per_1k(model)
    return (tokens / 1000.0) * price


# ──────────────────────────────────────────────────────────────────────
# S2-10: Budget reservation (pre-call)
# ──────────────────────────────────────────────────────────────────────

def reserve_budget(
    tenant_id: str,
    estimated_tokens: int,
    model: str,
    *,
    purpose_id: Optional[str] = None,
) -> float:
    """Reserve budget for an upcoming LLM call.

    Atomically decrements the tenant budget by the estimated cost.
    Returns the reserved amount (USD).

    Raises ``budget.BudgetExceededError`` if insufficient budget.
    """
    cost_est = estimate_cost(estimated_tokens, model)
    if cost_est <= 0:
        return 0.0

    # This will raise BudgetExceededError if insufficient
    budget.charge_usd(tenant_id, cost_est)
    logger.debug(
        "Reserved $%.4f for tenant %s (est. %d tokens, model=%s)",
        cost_est, tenant_id, estimated_tokens, model,
    )
    return cost_est


def release_reservation(
    tenant_id: str,
    reserved_amount: float,
    actual_tokens: int,
    model: str,
) -> float:
    """Settle a budget reservation after the LLM call completes.

    If the actual cost was less than reserved, the difference is refunded.
    If the actual cost was more, the additional amount is charged.

    Returns the net adjustment (positive = refund, negative = extra charge).
    """
    actual_cost = estimate_cost(actual_tokens, model)
    diff = reserved_amount - actual_cost

    if abs(diff) < 1e-6:
        return 0.0  # No adjustment needed

    if diff > 0:
        # Refund overpayment
        try:
            if budget._redis:
                budget._redis.incrbyfloat(budget._key_left(tenant_id), diff)
            else:
                with budget._store_lock:
                    if tenant_id in budget._store:
                        budget._store[tenant_id]["left"] += diff
            logger.debug(
                "Refunded $%.4f to tenant %s (reserved=%.4f, actual=%.4f)",
                diff, tenant_id, reserved_amount, actual_cost,
            )
        except Exception as exc:
            logger.warning("Budget refund failed for tenant %s: %s", tenant_id, exc)
    else:
        # Charge the additional amount
        try:
            budget.charge_usd(tenant_id, -diff)
        except budget.BudgetExceededError:
            logger.warning(
                "Tenant %s exceeded budget on settlement (extra $%.4f)",
                tenant_id, -diff,
            )

    return diff
