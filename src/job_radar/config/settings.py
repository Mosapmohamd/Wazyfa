"""Runtime settings. No hardcoded credentials, everything overridable by env."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="JOB_RADAR_", env_file=".env", extra="ignore"
    )

    sources_file: Path = PROJECT_ROOT / "config" / "sources.yaml"
    default_keyword: str = "AI Engineer"
    default_location: str = "Egypt"
    fetch_timeout_ms: int = 30_000
    log_level: str = "INFO"


settings = Settings()
