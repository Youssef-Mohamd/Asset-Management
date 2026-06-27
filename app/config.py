"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from .env file."""
    
    # Database
    DATABASE_URL: str = "postgresql://user:password@localhost:5432/asset_management"
    
    # API Authentication
    API_KEY: str = "my_super_secret_api_key_123"
    
    # Application
    DEBUG: bool = False
    LOG_LEVEL: str = "info"
    APP_TITLE: str = "Asset Management API"
    APP_VERSION: str = "1.0.0"

    class Config:
        """Load from .env file."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Load settings once
settings = Settings()

