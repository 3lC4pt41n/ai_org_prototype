"""Centralized application settings."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration, unified for all services."""

    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql+psycopg2://postgres:ai@db/ai_org"
    )
    redis_url: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    default_budget: float = float(os.getenv("DEFAULT_BUDGET", "500.0"))
    workspace_dir: Path = Path(
        os.getenv("WORKSPACE_DIR", "/app/workspace")
    ).resolve()
    token_price_per_1000: float = float(os.getenv("TOKEN_PRICE_PER_1000", "0.02"))

    # S6-01: Rate limiting
    rate_limit_per_minute: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
    rate_limit_burst: int = int(os.getenv("RATE_LIMIT_BURST", "10"))

    # S6-02: Security
    allowed_hosts: str = os.getenv("ALLOWED_HOSTS", "*")
    cors_max_age: int = int(os.getenv("CORS_MAX_AGE", "600"))

    # S6-06: Structured logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    log_format: str = os.getenv("LOG_FORMAT", "json")  # "json" or "text"

    # S6-09: Input sanitization
    max_request_body_bytes: int = int(
        os.getenv("MAX_REQUEST_BODY_BYTES", str(10 * 1024 * 1024))  # 10 MB
    )


@lru_cache()
def get_settings() -> "Settings":
    return Settings()


settings = get_settings()
