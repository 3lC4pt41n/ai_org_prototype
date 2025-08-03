"""Configuration utilities for ai_org_backend."""

from pydantic_settings import BaseSettings


class Config(BaseSettings):
    """Application environment configuration."""

    redis_url: str = "redis://:ai_redis_pw@localhost:6379/0"
    qdrant_url: str | None = None
    qdrant_api_key: str | None = None


config = Config()  # type: ignore

# Legacy module-level constants
REDIS_URL = config.redis_url
QDRANT_URL = config.qdrant_url
QDRANT_API_KEY = config.qdrant_api_key
