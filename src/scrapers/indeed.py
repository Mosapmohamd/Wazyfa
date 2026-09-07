"""Indeed job-board scraper (thin wrapper over the shared engine)."""

from __future__ import annotations

from src.scrapers.common import _country_name, _INDEED_DOMAINS
from src.scrapers.engine import CollectionResult
from src.scrapers.runner import run_source


def _domain_for(location: str) -> str:
    return _INDEED_DOMAINS.get(_country_name(location), "www.indeed.com")


def collect_indeed(keyword: str, location: str, headless: bool, network_idle: bool) -> CollectionResult:
    """Indeed uses a per-country domain, so base_url is patched per call."""
    domain = _domain_for(location)
    return run_source(
        "indeed",
        keyword,
        location,
        headless,
        network_idle,
        overrides={
            "base_url": f"https://{domain}",
            "search_url_template": (
                f"https://{domain}/jobs?q={{keyword}}&l={{location}}&fromage=1"
            ),
        },
    )


def scrape_indeed(keyword: str, location: str, headless: bool, network_idle: bool) -> list[dict[str, str]]:
    return collect_indeed(keyword, location, headless, network_idle).jobs
