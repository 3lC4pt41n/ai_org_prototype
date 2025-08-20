"""Configuration utilities for ai_org_backend."""

from pydantic_settings import BaseSettings


class Config(BaseSettings):
    """Application environment configuration."""

    redis_url: str
    qdrant_url: str | None = None
    qdrant_api_key: str | None = None
    # OpenAI API configuration
    openai_api_key: str | None = None
    openai_model_default: str = "o3"
    openai_model_pro: str = "o3-pro"
    openai_model_thinking: str = "o3"
    # Testing sandbox configuration
    test_timeout_seconds: int = 30
    test_cpu_limit: str = "1"
    test_memory_limit: str = "512m"


config = Config()  # type: ignore

# Legacy module-level constants
REDIS_URL = config.redis_url
QDRANT_URL = config.qdrant_url
QDRANT_API_KEY = config.qdrant_api_key
# OpenAI configuration constants
OPENAI_API_KEY = config.openai_api_key
OPENAI_MODEL_DEFAULT = config.openai_model_default
OPENAI_MODEL_PRO = config.openai_model_pro
OPENAI_MODEL_THINKING = config.openai_model_thinking
# Testing sandbox constants
TEST_TIMEOUT_SECONDS = config.test_timeout_seconds
TEST_CPU_LIMIT = config.test_cpu_limit
TEST_MEMORY_LIMIT = config.test_memory_limit
