"""Job search schemas."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from config import settings as project_settings
from src.job_filter import SUPPORTED_LEVELS

from app.schemas.common import JobBase


class JobListing(BaseModel):
    """A job listing. Extra keys (Job_Description, seniority_match...) are kept."""

    model_config = ConfigDict(extra="allow")

    Platform: str = "N/A"
    Title: str = "N/A"
    Company: str = "N/A"
    Link: str = "N/A"


class JobSearchRequest(BaseModel):
    keyword: str = Field(min_length=2, max_length=120, examples=["AI Engineer"])
    location: str = Field(
        default_factory=lambda: project_settings.location,
        min_length=2,
        max_length=120,
        examples=["Egypt"],
    )
    target_level: Optional[Literal[SUPPORTED_LEVELS]] = None
    target_role: str | None = Field(
        default=None,
        min_length=1,
        max_length=80,
    )

    @field_validator("keyword", "location")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty or whitespace")
        return value


class SearchResult(BaseModel):
    keyword: str
    location: str
    total_found: int
    total_after_filter: Optional[int] = None
    jobs: list[JobListing]


class SearchJobResponse(JobBase):
    result: SearchResult | None = None


class CachedJobsResponse(BaseModel):
    keyword: str
    location: str
    count: int
    jobs: list[JobListing]


# ── NEW: CV-driven search ──

class SearchFromCVRequest(BaseModel):
    """Start a search using the CV's extracted role and seniority.

    All override fields are optional; if omitted, the extracted
    profile values are used.
    """

    upload_id: str = Field(..., description="Upload ID returned by POST /cv/extract")
    keyword: str | None = Field(
        default=None, description="Override the extracted role as search keyword"
    )
    target_level: str | None = Field(
        default=None, description="Override the extracted seniority level"
    )
    target_role: str | None = Field(
        default=None,
        description="Override the target job role",
    )
    location: str | None = Field(
        default=None, description="Override the default location"
    )


class SearchFromCVResponse(JobBase):
    """Job status + the profile values that were used for the search."""

    extracted_role: str
    extracted_level: str
    used_keyword: str
    used_target_level: str
    used_location: str
    result: SearchResult | None = None
