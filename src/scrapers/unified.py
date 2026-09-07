"""Unified multi-board job search with caching, health reporting and a ledger."""

from __future__ import annotations

import concurrent.futures
import logging
from typing import Any

from src.cache_manager import system_cache
from src.cv_profile_extractor import extract_cv_profile
from src.job_ledger import job_ledger
from src.scrapers import bayt, indeed, jobzella, linkedin, wuzzuf
from src.scrapers.common import _deduplicate_jobs, annotate_cross_platform_duplicates
from src.scrapers.engine import CollectionResult
from src.scrapers.runner import run_source

logger = logging.getLogger(__name__)


def extract_search_profile_from_cv(cv_text: str) -> dict[str, Any]:
    """Infer the job keyword and seniority used by the scraper from CV text."""

    profile = extract_cv_profile(cv_text)
    profile["search_keyword"] = profile["role"]
    profile["search_target_level"] = profile["target_level"]
    return profile


def _collectors(keyword: str, location: str, headless: bool, network_idle: bool):
    """Each entry returns a CollectionResult, so failures stay visible."""

    return {
        "wuzzuf": lambda: run_source("wuzzuf", keyword, location, headless, network_idle),
        "linkedin": lambda: run_source("linkedin", keyword, location, headless, network_idle),
        "indeed": lambda: indeed.collect_indeed(keyword, location, headless, network_idle),
        "bayt": lambda: bayt.collect_bayt(keyword, location, headless, network_idle),
        "jobzella": lambda: run_source("jobzella", keyword, location, headless, network_idle),
    }


def collect_all(
    keyword: str = "AI Engineer",
    location: str = "Egypt",
    headless: bool = True,
    network_idle: bool = True,
) -> tuple[list[dict[str, str]], list[CollectionResult]]:
    """Scrape every board concurrently and return jobs plus per-source health."""

    results: list[CollectionResult] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(fn): name
            for name, fn in _collectors(keyword, location, headless, network_idle).items()
        }
        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:
                # A collector should never raise; if one does, that is itself
                # a defect worth surfacing rather than logging and moving on.
                logger.exception("%s collector raised unexpectedly", name)
                results.append(
                    CollectionResult(source=name, fatal_error=f"{type(exc).__name__}: {exc}")
                )

    jobs = [job for result in results for job in result.jobs]
    return jobs, results


def unified_job_scraper(
    keyword: str = "AI Engineer",
    location: str = "Egypt",
    headless: bool = True,
    network_idle: bool = True,
) -> list[dict[str, str]]:
    """Scrape all configured sources, cache successful runs, and tag new jobs."""

    cached_jobs = system_cache.get_cached_search(keyword, location, max_hours=24)
    if cached_jobs is not None:
        logger.info("Loaded %d jobs from the local cache", len(cached_jobs))
        return cached_jobs

    logger.info("Scraping jobs for %r in %r", keyword, location)
    jobs, results = collect_all(keyword, location, headless, network_idle)

    jobs = _deduplicate_jobs(jobs)
    jobs = annotate_cross_platform_duplicates(jobs)
    jobs = job_ledger.annotate(jobs)

    healthy = [r for r in results if r.is_healthy or r.status == "degraded"]
    broken = [r for r in results if not r.is_healthy and r.status != "degraded"]

    if broken:
        logger.error(
            "%d/%d sources are broken: %s",
            len(broken),
            len(results),
            ", ".join(f"{r.source}({r.status})" for r in broken),
        )

    # Only cache a run we can stand behind. The previous behaviour cached
    # empty results unconditionally, which meant a broken scraper poisoned
    # the cache and looked identical to a quiet day on the job market.
    if healthy:
        system_cache.set_cached_search(keyword, location, jobs)
    else:
        logger.error(
            "Every source failed -- refusing to cache this run. "
            "Check selectors in src/scrapers/config/sources.yaml."
        )

    new_count = sum(1 for job in jobs if job.get("is_new"))
    logger.info(
        "Discovered %d jobs across %d/%d healthy sources (%d new)",
        len(jobs),
        len(healthy),
        len(results),
        new_count,
    )
    return jobs
