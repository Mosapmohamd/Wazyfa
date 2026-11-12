"""Job search orchestration. Wraps existing scraper and filter."""

from __future__ import annotations

import logging
from typing import Any

from config import settings as project_settings
from src.job_filter import filter_jobs
from src.job_scraper import unified_job_scraper

logger = logging.getLogger(__name__)


def execute_search(
    *,
    keyword: str,
    location: str,
    target_level: str | None = None,
    target_role: str | None = None,
) -> dict[str, Any]:
    """Scrape all platforms (cache-aware) and optionally filter by seniority."""

    jobs = unified_job_scraper(
        keyword=keyword,
        location=location,
        headless=project_settings.headless,
        network_idle=project_settings.network_idle,
    )
    total_found = len(jobs)

    if target_level or target_role:
        jobs = filter_jobs(
            jobs,
            target_level or "Any",
            target_role or "Any",
        )

    logger.info(
        "Search finished: %d found, %d after filter for %r/%r",
        total_found, len(jobs), keyword, location,
    )
    return {
        "keyword": keyword,
        "location": location,
        "total_found": total_found,
        "total_after_filter": len(jobs) if target_level else None,
        "jobs": jobs,
    }
