"""Wuzzuf job-board scraper (thin wrapper over the shared engine)."""

from __future__ import annotations

from src.scrapers.runner import run_source


def scrape_wuzzuf(keyword: str, location: str, headless: bool, network_idle: bool) -> list[dict[str, str]]:
    return run_source("wuzzuf", keyword, location, headless, network_idle).jobs
