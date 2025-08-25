"""
ai_org_backend package init

Wir aktivieren hier frühzeitig Kompatibilität für Redis, sodass alte Aufrufer
von 'decrbyfloat' weiterhin funktionieren (intern via incrbyfloat mit negativem Wert).
"""
try:
    from .compat.redis_compat import ensure_redis_decrbyfloat as _ensure_redis_compat  # type: ignore
    _ensure_redis_compat()
except Exception as _e:  # pragma: no cover
    import logging; logging.getLogger(__name__).warning("Redis compat patch not applied: %s", _e)

__all__ = []
