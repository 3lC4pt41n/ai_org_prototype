import redis

from ai_org_backend.config import config
from ai_org_backend.settings import settings

# Shared Redis connection pool and application defaults
pool = redis.from_url(config.redis_url, decode_responses=True)
DEFAULT_BUDGET = settings.default_budget
