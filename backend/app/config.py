"""
Application configuration using Pydantic Settings.
Loads environment variables from .env file.
"""

from functools import lru_cache
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_env: Literal["development", "staging", "production"] = "development"
    app_debug: bool = True
    app_secret_key: str = "dev-secret-key-change-in-production"
    app_name: str = "PDF to DOCX Converter"
    app_version: str = "1.0.0"

    # API Keys - OCR Services
    mistral_api_key: str = ""
    deepseek_api_key: str = ""

    # Database
    database_url: str = "sqlite:///./app.db"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Storage
    storage_type: Literal["local", "s3"] = "local"
    storage_path: str = "./storage"
    s3_endpoint: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_bucket: str | None = None
    s3_region: str = "us-east-1"

    # Processing Settings
    max_file_size_mb: int = 100
    max_pages_per_job: int = 200
    max_concurrent_jobs: int = 5

    # OCR Settings
    default_ocr_provider: Literal["mistral", "deepseek", "surya"] = "mistral"
    ocr_timeout_seconds: int = 300

    # CORS
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    # Rate Limiting
    rate_limit_per_minute: int = 30

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins.split(",")]

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.app_env == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.app_env == "production"

    @property
    def max_file_size_bytes(self) -> int:
        """Convert max file size to bytes."""
        return self.max_file_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.
    Uses lru_cache to avoid reading .env file on every request.
    """
    return Settings()


# Global settings instance for easy import
settings = get_settings()
