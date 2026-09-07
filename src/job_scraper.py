"""Backward-compatible shim: the scrapers now live in the src.scrapers package."""

from src.scrapers import (  # noqa: F401
    extract_search_profile_from_cv,
    scrape_bayt,
    scrape_indeed,
    scrape_jobzella,
    scrape_linkedin,
    scrape_wuzzuf,
    unified_job_scraper,
)

__all__ = [
    "extract_search_profile_from_cv",
    "scrape_bayt",
    "scrape_indeed",
    "scrape_jobzella",
    "scrape_linkedin",
    "scrape_wuzzuf",
    "unified_job_scraper",
]
