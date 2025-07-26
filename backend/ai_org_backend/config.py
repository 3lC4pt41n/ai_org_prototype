"""Configuration utilities for ai_org_backend."""

from pydantic_settings import BaseSettings


class Config(BaseSettings):
    """Application environment configuration."""

    redis_url: str = "redis://:ai_redis_pw@localhost:6379/0"


config = Config()  # type: ignore

# Legacy module-level constants
REDIS_URL = config.redis_url
