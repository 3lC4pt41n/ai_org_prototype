from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Application configuration."""
    default_budget: float = 20.0

settings = Settings()
