"""Central configuration for the AI Job Skill Gap Analyzer.

Pipeline settings live here, backed by pydantic-settings so every value can be
overridden through environment variables (or a local `.env` file). API-layer
settings (CORS, upload limits) remain in `app/core/config.py`.

Legacy environment variable names are preserved via aliases (e.g.
`SCRAPER_HEADLESS`, `LLM_USE_4BIT`, `AZURE_OPENAI_API_KEY`).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Pipeline settings with safe local-development defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Search parameters
    keyword: str = "Backend Developer"
    location: str = "Egypt"
    target_level: str = "Junior"
    target_role: str = "Any"

    # File paths
    data_dir: Path = Path("data")
    cv_path: Path = Path("data/resume.pdf")
    filtered_excel: Path = Path("data/Filtered_AI_Jobs_Junior.xlsx")
    enriched_excel: Path = Path("data/Jobs_with_Descriptions.xlsx")
    checkpoint_excel: Path = Path("data/Jobs_Checkpoint.xlsx")
    final_report_txt: Path = Path("data/Final_Skill_Gap_Report.txt")

    # Scraping behavior
    headless: bool = Field(
        default=True,
        validation_alias=AliasChoices("SCRAPER_HEADLESS", "headless"),
    )
    network_idle: bool = Field(
        default=True,
        validation_alias=AliasChoices("SCRAPER_NETWORK_IDLE", "network_idle"),
    )
    min_delay: float = 4.5
    max_delay: float = 8.7
    checkpoint_interval: int = 5

    # Summarization model
    primary_summarizer: str = "allenai/led-base-16384"
    fallback_summarizer: str = "facebook/bart-large-cnn"
    max_summary_tokens: int = 400
    min_summary_tokens: int = 100

    # Memory-constrained escape hatch for the Hugging Face summarizer
    skip_hf_summarizer: bool = Field(
        default=False,
        validation_alias=AliasChoices("SKIP_HF_SUMMARIZER", "skip_hf_summarizer"),
    )

    # Local language model
    llm_model: str = "microsoft/Phi-3-mini-4k-instruct"
    use_4bit: bool = Field(
        default=False,
        validation_alias=AliasChoices("LLM_USE_4BIT", "use_4bit"),
    )
    llm_max_new_tokens: int = 2560

    # External LLM provider selection.
    # Supported providers: "nvidia", "openai", "anthropic", "google", "azure", "custom"
    llm_provider: str = "nvidia"

    # NVIDIA NIM. Keep credentials outside source control.
    nvidia_api_key: str = ""
    nvidia_fallback_model: str = "meta/llama-3.1-70b-instruct"
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-haiku-20240307"

    # Google Gemini
    google_api_key: str = ""
    google_model: str = "gemini-1.5-flash"

    # Azure OpenAI
    azure_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("AZURE_OPENAI_API_KEY", "azure_api_key"),
    )
    azure_endpoint: str = Field(
        default="",
        validation_alias=AliasChoices("AZURE_OPENAI_ENDPOINT", "azure_endpoint"),
    )
    azure_deployment: str = Field(
        default="",
        validation_alias=AliasChoices("AZURE_OPENAI_DEPLOYMENT", "azure_deployment"),
    )
    azure_api_version: str = "2024-02-15-preview"

    # Custom OpenAI-compatible API
    custom_api_key: str = ""
    custom_base_url: str = ""
    custom_model: str = ""

    # Explicit opt-in required to send CV/Job data to external AI providers
    allow_external_ai: bool = False

    # Description limits
    max_desc_chars: int = 4000

    def ensure_dirs(self) -> None:
        """Create the configured data directory when it does not exist."""

        self.data_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()