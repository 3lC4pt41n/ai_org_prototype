"""
Per-tenant budget management:
- Store budget values in Redis (in-memory fallback if Redis is unavailable).
- Provide get_total/get_left/set_total/charge() and a BudgetExceededError exception.
- Calculate costs based on token usage and configured prices.
"""

from __future__ import annotations

import json
import os
import threading
from typing import Dict

try:  # pragma: no cover - optional redis import
    import redis  # type: ignore
except Exception:  # pragma: no cover
    redis = None  # type: ignore

# -----------------------------
# Configuration / Pricing
# -----------------------------
USD_PER_1K_TOKENS = float(os.getenv("USD_PER_1K_TOKENS", "0.0025"))
PRICING_MAP: Dict[str, float] = {}
try:  # pragma: no cover - best effort
    raw = os.getenv("OPENAI_PRICING_JSON")
    if raw:
        PRICING_MAP = json.loads(raw)
except Exception:  # pragma: no cover
    PRICING_MAP = {}

# ── Built-in Anthropic pricing (USD per 1K tokens, blended input+output) ──
# Users can override via OPENAI_PRICING_JSON; these are sensible defaults.
_ANTHROPIC_DEFAULTS: Dict[str, float] = {
    "claude-opus-4":      0.060,
    "claude-sonnet-4":    0.012,
    "claude-3.5-sonnet":  0.012,
    "claude-3-5-sonnet":  0.012,
    "claude-3.5-haiku":   0.003,
    "claude-3-5-haiku":   0.003,
    "claude-3-haiku":     0.001,
    "claude-3-opus":      0.060,
    "claude-3-sonnet":    0.012,
}
for _k, _v in _ANTHROPIC_DEFAULTS.items():
    PRICING_MAP.setdefault(_k, _v)

DEFAULT_BUDGET = float(os.getenv("BUDGET_DEFAULT_USD", "10.0"))


class BudgetExceededError(Exception):
    """Raised when there is no budget left for a tenant."""


def _create_redis():
    url = os.getenv("REDIS_URL")
    if not url or not redis:
        return None
    try:
        r = redis.Redis.from_url(url, decode_responses=True)
        r.ping()
        return r
    except Exception:  # pragma: no cover
        return None


_redis = _create_redis()
_store_lock = threading.Lock()
_store: Dict[str, Dict[str, float]] = {}


def _key_total(tid: str) -> str:
    return f"ai_org:tenant:{tid}:budget_total"


def _key_left(tid: str) -> str:
    return f"ai_org:tenant:{tid}:budget_left"


def get_price_per_1k(model: str) -> float:
    if not model:
        return USD_PER_1K_TOKENS
    if model in PRICING_MAP:
        return PRICING_MAP[model]
    for k, v in PRICING_MAP.items():
        if model.startswith(k):
            return v
    return USD_PER_1K_TOKENS


def ensure_initialized(tid: str) -> None:
    if _redis:
        pipe = _redis.pipeline()
        if not _redis.exists(_key_total(tid)):
            pipe.set(_key_total(tid), DEFAULT_BUDGET)
        if not _redis.exists(_key_left(tid)):
            pipe.set(_key_left(tid), DEFAULT_BUDGET)
        pipe.execute()
    else:
        with _store_lock:
            _store.setdefault(tid, {"total": DEFAULT_BUDGET, "left": DEFAULT_BUDGET})


def get_total(tid: str) -> float:
    ensure_initialized(tid)
    if _redis:
        return float(_redis.get(_key_total(tid)) or 0.0)
    with _store_lock:
        return _store[tid]["total"]


def get_left(tid: str) -> float:
    ensure_initialized(tid)
    if _redis:
        return float(_redis.get(_key_left(tid)) or 0.0)
    with _store_lock:
        return _store[tid]["left"]


def set_total(tid: str, total_usd: float) -> None:
    if _redis:
        pipe = _redis.pipeline()
        pipe.set(_key_total(tid), total_usd)
        left = float(_redis.get(_key_left(tid)) or 0.0)
        if left > total_usd:
            pipe.set(_key_left(tid), total_usd)
        pipe.execute()
    else:
        with _store_lock:
            left = _store.get(tid, {}).get("left", total_usd)
            _store[tid] = {"total": total_usd, "left": min(left, total_usd)}


def charge_tokens(tid: str, model: str, tokens: int) -> float:
    if tokens <= 0:
        return 0.0
    price = get_price_per_1k(model)
    usd = (tokens / 1000.0) * price
    charge_usd(tid, usd)
    return usd


def charge_usd(tid: str, usd: float) -> None:
    ensure_initialized(tid)
    left = get_left(tid)
    if left <= 0.0 and usd > 0:
        raise BudgetExceededError(f"Tenant {tid} has no remaining budget.")
    if _redis:
        new_left = _redis.decrbyfloat(_key_left(tid), usd)
        if new_left < -1e-6:
            _redis.incrbyfloat(_key_left(tid), usd)
            raise BudgetExceededError(f"Tenant {tid} exceeded budget.")
    else:
        with _store_lock:
            cur = _store[tid]["left"]
            if cur - usd < -1e-6:
                raise BudgetExceededError(f"Tenant {tid} exceeded budget.")
            _store[tid]["left"] = cur - usd
