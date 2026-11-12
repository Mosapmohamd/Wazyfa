"""Bayt job-board scraper (thin wrapper over the shared engine).

The previous implementation had no `return` statement at the end of the
function, so it returned None. `unified.py` then called `.extend(None)`,
raising TypeError, which was caught and logged as an unexpected failure.
Bayt therefore contributed zero jobs on every run.
"""

from __future__ import annotations

from src.scrapers.common import _bayt_country_slug
from src.scrapers.engine import CollectionResult
from src.scrapers.runner import run_source


def collect_bayt(keyword: str, location: str, headless: bool, network_idle: bool) -> CollectionResult:
    return run_source(
        "bayt",
        keyword,
        location,
        headless,
        network_idle,
        url_extra={"country_slug": _bayt_country_slug(location)},
    )


def scrape_bayt(keyword: str, location: str, headless: bool, network_idle: bool) -> list[dict[str, str]]:
    return collect_bayt(keyword, location, headless, network_idle).jobs
