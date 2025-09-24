"""Repository helpers and budget accounting utilities."""

from __future__ import annotations

import logging
from typing import Optional

from ai_org_backend.metrics import BUDGET_GA
from ai_org_backend.redis_client import DEFAULT_BUDGET, pool
from ai_org_backend.repo import Repo as _Repo

__all__ = ["Repo", "budget_left", "debit"]

logger = logging.getLogger(__name__)

# Re-export the core Repo implementation so callers can import from services.
Repo = _Repo


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):  # pragma: no cover - defensive fallback
        return default


def budget_left(tenant: str = "demo", purpose: Optional[str] = None) -> float:
    """Return remaining budget for a tenant or specific purpose."""

    if pool is None:
        return float(DEFAULT_BUDGET) if purpose else 0.0

    if purpose:
        try:
            raw = pool.get(f"budget:{tenant}:{purpose}")
        except Exception:  # pragma: no cover - redis errors are non-fatal
            logger.exception("Failed to read budget for tenant %s purpose %s", tenant, purpose)
            return float(DEFAULT_BUDGET)
        return _safe_float(raw, float(DEFAULT_BUDGET))

    total = 0.0
    try:
        for key in pool.keys(f"budget:{tenant}:*"):
            total += _safe_float(pool.get(key), 0.0)
    except Exception:  # pragma: no cover - redis errors are non-fatal
        logger.exception("Failed to aggregate budgets for tenant %s", tenant)
        return total
    return total


def debit(tenant: str, amount: float, purpose: Optional[str] = None) -> None:
    """Decrease the available budget for a tenant and emit telemetry."""

    if amount <= 0:
        return

    if pool is None:
        logger.warning("Redis pool unavailable; skipping budget debit for tenant %s", tenant)
        return

    left: float
    try:
        if purpose:
            current = _safe_float(pool.get(f"budget:{tenant}:{purpose}"), float(DEFAULT_BUDGET))
            left = max(current - amount, 0.0)
            pool.set(f"budget:{tenant}:{purpose}", left)
        else:
            left = budget_left(tenant)
    except Exception:  # pragma: no cover - redis errors are non-fatal
        logger.exception("Failed to debit budget for tenant %s", tenant)
        return

    try:
        BUDGET_GA.labels(tenant).set(left)
    except Exception:  # pragma: no cover - metrics failures are best effort
        logger.debug("Failed to emit budget gauge for tenant %s", tenant)
