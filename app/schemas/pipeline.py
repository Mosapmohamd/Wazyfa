"""Full-pipeline schemas."""

from __future__ import annotations

from pydantic import BaseModel

from app.schemas.common import JobBase


class PipelineResult(BaseModel):
    keyword: str
    target_level: str
    location: str
    jobs_found: int
    jobs_filtered: int
    market_summary: str
    report: str
    report_path: str | None = None
    run_id: str | None = None
    run_directory: str | None = None


class PipelineJobResponse(JobBase):
    result: PipelineResult | None = None
