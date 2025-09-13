"""
ai_org_backend package init

Enable Redis compatibility early so older callers of 'decrbyfloat' continue to
work (internally via incrbyfloat with a negative value).
"""

from typing import List

try:
    from .compat.redis_compat import (
        ensure_redis_decrbyfloat as _ensure_redis_compat,  # type: ignore
    )

    _ensure_redis_compat()
except Exception as _e:  # pragma: no cover
    import logging

    logging.getLogger(__name__).warning("Redis compat patch not applied: %s", _e)

__all__: List[str] = []
