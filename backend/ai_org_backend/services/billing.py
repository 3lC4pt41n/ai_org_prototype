"""Simple Redis-backed budget helpers."""

from ai_org_backend.main import DEFAULT_BUDGET, pool

_MEM: dict[str, float] = {}


def balance(tenant: str) -> float:
    """Return current budget for tenant."""
    try:
        return float(pool.hget("budget", tenant) or DEFAULT_BUDGET)
    except Exception:
        return _MEM.get(tenant, DEFAULT_BUDGET)


def credit(tenant: str, amount: float) -> None:
    """Increase budget by given amount."""
    new_balance = balance(tenant) + amount
    try:
        pool.hset("budget", tenant, new_balance)
    except Exception:
        _MEM[tenant] = new_balance


def charge(tenant: str, amount: float) -> float:
    """Deduct `amount` from tenant budget and return remaining balance."""
    new_balance = balance(tenant) - amount
    try:
        pool.hset("budget", tenant, new_balance)
    except Exception:
        _MEM[tenant] = new_balance
    return new_balance
