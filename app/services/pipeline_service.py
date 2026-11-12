"""Full CV-to-skill-gap pipeline orchestration.

The pipeline adds job discovery (scraping) on top of the shared
gap-analysis chain in `analysis_service.execute_analysis`, which owns the
filter → enrich → summarize → analyze stages and run-scoped artifacts.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.core.exceptions import AppError, CVExtractionError
from app.services.analysis_service import execute_analysis
from config import settings as project_settings
from src.cv_extractor import extract_cv_text
from src.job_scraper import unified_job_scraper

logger = logging.getLogger(__name__)


def execute_pipeline(
    *,
    cv_path: str | Path,
    keyword: str,
    target_level: str,
    target_role: str | None = None,
    location: str | None = None,
) -> dict[str, Any]:
    """Run the complete pipeline and return a structured result.

    Creates an isolated run directory to avoid concurrent file conflicts.
    """

    location = location or project_settings.location

    cv_text = extract_cv_text(cv_path)
    if not cv_text:
        raise CVExtractionError(
            "Could not extract text from the CV. It may be missing, image-only, or corrupted."
        )

    logger.info("Scraping jobs for %r in %r", keyword, location)
    all_jobs = unified_job_scraper(
        keyword=keyword,
        location=location,
        headless=project_settings.headless,
        network_idle=project_settings.network_idle,
    )
    if not all_jobs:
        raise AppError(
            f"No jobs found for {keyword!r} in {location!r}. Try another keyword or location.",
            status_code=422,
        )

    # Delegate the filter → enrich → summarize → analyze chain (shared with
    # the analysis-only endpoint); the pre-extracted CV avoids a second parse.
    result = execute_analysis(
        cv_path=cv_path,
        jobs=all_jobs,
        keyword=keyword,
        target_level=target_level,
        target_role=target_role,
        location=location,
        cv_text=cv_text,
    )
    logger.info("Pipeline completed; report saved to %s", result["report_path"])
    return result
