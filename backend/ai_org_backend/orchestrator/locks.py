"""S2-01: Distributed Redis locks for orchestrator phase transitions.

Prevents race conditions when multiple orchestrator instances (or rapid
polling cycles) attempt to transition the same purpose through pipeline
phases simultaneously.

Usage::

    with phase_lock(tenant_id, purpose_id, "architecture") as acquired:
        if not acquired:
            return  # another process holds the lock
        # ... perform phase transition ...
"""

from __future__ import annotations

import contextlib
import logging
import uuid
from typing import Generator

from ai_org_backend.redis_client import pool

logger = logging.getLogger(__name__)

# S-Sprint3 Fix #3: Lock TTL raised to match TASK_SOFT_TIME_LIMIT (300s)
# to prevent premature lock expiry during long-running dispatches.
_LOCK_TTL_S = 300  # 5 minutes


def _lock_key(tenant_id: str, purpose_id: str, phase: str) -> str:
    return f"lock:phase:{tenant_id}:{purpose_id}:{phase}"


def acquire_lock(
    tenant_id: str,
    purpose_id: str,
    phase: str,
    *,
    ttl: int = _LOCK_TTL_S,
    token: str | None = None,
) -> str | None:
    """Try to acquire a distributed lock.  Returns a token on success, None on failure."""
    if pool is None:
        # No Redis – degrade gracefully (single-process mode)
        return "local"
    token = token or uuid.uuid4().hex
    key = _lock_key(tenant_id, purpose_id, phase)
    try:
        ok = pool.set(key, token, nx=True, ex=ttl)
        if ok:
            logger.debug("Acquired lock %s (token=%s, ttl=%ds)", key, token[:8], ttl)
            return token
        logger.debug("Lock %s already held – skipping", key)
        return None
    except Exception as exc:
        logger.error("Failed to acquire lock %s: %s", key, exc)
        # Fail-open: allow progress in case Redis is down
        return "local"


def release_lock(
    tenant_id: str, purpose_id: str, phase: str, token: str
) -> bool:
    """Release a lock only if we still own it (compare-and-delete)."""
    if pool is None or token == "local":
        return True
    key = _lock_key(tenant_id, purpose_id, phase)
    # Lua script for atomic compare-and-delete
    lua = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("del", KEYS[1])
    else
        return 0
    end
    """
    try:
        result = pool.eval(lua, 1, key, token)
        released = bool(result)
        if released:
            logger.debug("Released lock %s (token=%s)", key, token[:8])
        else:
            logger.warning("Lock %s not released – token mismatch", key)
        return released
    except Exception as exc:
        logger.error("Failed to release lock %s: %s", key, exc)
        return False


@contextlib.contextmanager
def phase_lock(
    tenant_id: str,
    purpose_id: str,
    phase: str,
    *,
    ttl: int = _LOCK_TTL_S,
) -> Generator[bool, None, None]:
    """Context manager that acquires/releases a phase-transition lock.

    Yields ``True`` if the lock was acquired, ``False`` otherwise.
    The caller should check the value and skip work when ``False``.
    """
    token = acquire_lock(tenant_id, purpose_id, phase, ttl=ttl)
    acquired = token is not None
    try:
        yield acquired
    finally:
        if acquired and token:
            release_lock(tenant_id, purpose_id, phase, token)


def renew_lock(
    tenant_id: str,
    purpose_id: str,
    phase: str,
    token: str,
    *,
    ttl: int = _LOCK_TTL_S,
) -> bool:
    """S-Sprint3 Fix #3: Renew (extend) a held lock's TTL.

    Only extends if we still own the lock (compare token first).
    Called periodically (e.g. every 30s) by the lock holder to prevent
    premature expiry during long-running phase transitions.
    """
    if pool is None or token == "local":
        return True
    key = _lock_key(tenant_id, purpose_id, phase)
    lua = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("expire", KEYS[1], ARGV[2])
    else
        return 0
    end
    """
    try:
        result = pool.eval(lua, 1, key, token, str(ttl))
        renewed = bool(result)
        if renewed:
            logger.debug("Renewed lock %s (token=%s, ttl=%ds)", key, token[:8], ttl)
        else:
            logger.warning("Lock %s renewal failed – token mismatch", key)
        return renewed
    except Exception as exc:
        logger.error("Failed to renew lock %s: %s", key, exc)
        return False


def task_dispatch_lock(
    tenant_id: str, task_id: str, *, ttl: int = _LOCK_TTL_S
) -> str | None:
    """Acquire a one-shot lock to prevent duplicate task dispatches.

    S-Sprint3 Fix #3: TTL aligned with _LOCK_TTL_S (300s) instead of
    the previous hard-coded 60s.
    """
    if pool is None:
        return "local"
    key = f"lock:dispatch:{tenant_id}:{task_id}"
    token = uuid.uuid4().hex
    try:
        ok = pool.set(key, token, nx=True, ex=ttl)
        return token if ok else None
    except Exception as exc:
        logger.error("Failed to acquire dispatch lock for task %s: %s", task_id, exc)
        return "local"
