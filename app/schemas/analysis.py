"""Schemas for the independent analysis stages."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.common import JobBase, JobStatus
from app.schemas.cv import MatchedSignals


# ────────────────────── Gap analysis (market-based) ──────────────────────

class AnalysisRunRequest(BaseModel):
    """Request to run a full gap analysis using jobs from a prior search."""

    cv_upload_id: str = Field(..., description="Upload ID returned by POST /cv/extract")
    search_job_id: str = Field(
        ..., description="Job ID of a completed search returned by POST /jobs/search"
    )
    keyword: str | None = Field(
        default=None, description="Override keyword for report metadata"
    )
    target_level: str | None = Field(
        default=None, description="Filter jobs by seniority before analysis"
    )
    target_role: str | None = Field(
        default=None, description="Filter jobs by target role before analysis"
    )
    location: str | None = Field(
        default=None, description="Override location for report metadata"
    )


class AnalysisResult(BaseModel):
    run_id: str
    keyword: str
    target_level: str | None = None
    location: str
    jobs_found: int
    jobs_filtered: int
    market_summary: str
    report: str
    report_path: str | None = None
    run_directory: str | None = None


class AnalysisJobResponse(JobBase):
    result: AnalysisResult | None = None


# ────────────────────── CV-only direct analysis ──────────────────────

class CVDirectAnalysisRequest(BaseModel):
    upload_id: str = Field(..., description="Upload ID returned by POST /cv/extract")


class CVDirectAnalysisResult(BaseModel):
    upload_id: str
    role: str
    target_level: str
    skills: list[str]
    matched_signals: MatchedSignals
    extracted_chars: int
    review: str = Field(
        ..., description="JSON text containing skills, strengths, missing info, recommended roles"
    )


class CVDirectJobResponse(JobBase):
    result: CVDirectAnalysisResult | None = None


# ────────────────────── Independent description fetch ──────────────────────

class DescriptionFetchRequest(BaseModel):
    """Either provide jobs directly or reference a completed search job."""

    jobs: list[dict[str, Any]] | None = Field(
        default=None, description="List of job dicts with Title/Link/Platform"
    )
    search_job_id: str | None = Field(
        default=None, description="Job ID of a completed search to pull jobs from"
    )


class DescriptionFetchResult(BaseModel):
    run_id: str
    job_count: int
    enriched_jobs: list[dict[str, Any]]
    enriched_excel_path: str | None = None
    run_directory: str | None = None


class DescriptionFetchJobResponse(JobBase):
    result: DescriptionFetchResult | None = None


# ────────────────────── Independent market summarization ──────────────────────

class MarketSummaryRequest(BaseModel):
    """Either provide enriched jobs directly or reference a completed description-fetch job."""

    enriched_jobs: list[dict[str, Any]] | None = Field(
        default=None, description="List of enriched job dicts with Job_Description"
    )
    description_job_id: str | None = Field(
        default=None, description="Job ID of a completed description-fetch to pull enriched jobs from"
    )


class MarketSummaryResult(BaseModel):
    run_id: str
    job_count: int
    market_summary: str
    run_directory: str | None = None


class MarketSummaryJobResponse(JobBase):
    result: MarketSummaryResult | None = None
