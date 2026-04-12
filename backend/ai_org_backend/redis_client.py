import logging
import redis

from ai_org_backend.config import config
from ai_org_backend.settings import settings

log = logging.getLogger(__name__)

# Shared Redis connection pool and application defaults
pool = redis.from_url(config.redis_url, decode_responses=True)
DEFAULT_BUDGET = settings.default_budget


def redis_healthy() -> bool:
    """Return True if Redis is reachable and responding to PING.

    Used as a pre-flight check before dispatching tasks to avoid
    silent failures when the broker is down.
    """
    try:
        return pool.ping()
    except (redis.ConnectionError, redis.TimeoutError, redis.RedisError) as exc:
        log.error("Redis health check failed: %s", exc)
        return False
