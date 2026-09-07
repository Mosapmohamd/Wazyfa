"""Jobzella job-board scraper (thin wrapper over the shared engine).

Like Bayt, the previous implementation was missing its `return` statement and
silently contributed nothing.
"""

from __future__ import annotations

from src.scrapers.runner import run_source


def scrape_jobzella(keyword: str, location: str, headless: bool, network_idle: bool) -> list[dict[str, str]]:
    return run_source("jobzella", keyword, location, headless, network_idle).jobs
