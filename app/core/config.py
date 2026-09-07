"""API-layer configuration. Pipeline behavior stays in the project's config.py."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiSettings(BaseSettings):
    """API settings, loaded from environment variables prefixed with API_."""

    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="API_", extra="ignore"
    )

    app_name: str = "AI Job Skill Gap Analyzer API"
    api_v1_prefix: str = "/api/v1"
    debug: bool = False

    # Accept as string, parse in validator
    cors_origins: str = Field(default="", description="Comma-separated CORS origins")

    upload_dir: Path = Path("data/uploads")
    max_upload_size_mb: int = 10
    job_history_limit: int = 200

    @field_validator("cors_origins", mode="after")
    @classmethod
    def _parse_cors_origins(cls, value: str) -> str:
        # Keep as string here, we'll parse it in create_app
        return value


@lru_cache
def get_api_settings() -> ApiSettings:
    return ApiSettings()


def get_cors_origins() -> list[str]:
    """Parse CORS origins from settings."""
    value = api_settings.cors_origins
    if not value or not isinstance(value, str):
        return []
    return [origin.strip() for origin in value.split(",") if origin.strip()]


api_settings = get_api_settings()
