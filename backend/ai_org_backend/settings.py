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
        os.getenv("WORKSPACE_DIR", "/app/ai_org_backend/workspace")
    ).expanduser().resolve()


@lru_cache()
def get_settings() -> "Settings":
    return Settings()


settings = get_settings()
