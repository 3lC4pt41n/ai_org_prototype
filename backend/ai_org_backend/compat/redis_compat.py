"""
Backfill for 'decrbyfloat' in redis-py:
Redis has no DECRBYFLOAT; the correct command is INCRBYFLOAT with a negative value.
Some code paths call 'decrbyfloat'. This module adds the method to
Redis/StrictRedis/Pipeline if it's missing.
"""

from __future__ import annotations

from typing import Any


def ensure_redis_decrbyfloat() -> None:
    try:
        pass  # type: ignore
    except Exception:
        # redis not installed: nothing to do
        return

    def _impl(self: Any, name: str, amount: float = 1.0) -> float:
        """
        Decrement a float value using INCRBYFLOAT with a negative amount.
        Return the new value as float (like incrbyfloat).
        """
        try:
            amt = float(amount)
        except Exception:
            amt = 0.0
        # redis-py gibt float als Python-Float zurück
        return self.incrbyfloat(name, -amt)  # type: ignore[attr-defined]

    for cls in _iter_target_classes():
        if not hasattr(cls, "decrbyfloat"):
            try:
                setattr(cls, "decrbyfloat", _impl)
            except Exception:
                # Prefer to continue silently rather than block import
                pass  # nosec


def _iter_target_classes():
    """Helper: yield Redis, StrictRedis, Pipeline if available."""
    try:
        from redis.client import Pipeline, Redis, StrictRedis  # type: ignore

        yield Redis
        yield StrictRedis
        yield Pipeline
    except Exception:
        return


# Activate immediately on module import (idempotent)
try:
    ensure_redis_decrbyfloat()
except Exception:
    pass  # nosec
