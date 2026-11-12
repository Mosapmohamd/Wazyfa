"""Bridge between a source name and a CollectionResult."""

from __future__ import annotations

import logging
from typing import Any

from src.scrapers.common import _is_relevant_job
from src.scrapers.engine import (
    CollectionResult,
    ScraplingFetcher,
    SourceConfig,
    collect,
    load_sources,
)

logger = logging.getLogger(__name__)

_SOURCES: dict[str, SourceConfig] | None = None


def get_sources() -> dict[str, SourceConfig]:
    global _SOURCES
    if _SOURCES is None:
        _SOURCES = load_sources()
    return _SOURCES


def run_source(
    name: str,
    keyword: str,
    location: str,
    headless: bool = True,
    network_idle: bool = True,
    overrides: dict[str, Any] | None = None,
    url_extra: dict[str, str] | None = None,
) -> CollectionResult:
    source = get_sources().get(name)
    if source is None:
        return CollectionResult(source=name, fatal_error=f"unknown source {name!r}")
    if overrides:
        source = source.model_copy(update=overrides)
    if not source.enabled:
        return CollectionResult(source=source.platform_label, fatal_error="disabled")

    logger.info("Fetching jobs from %s", source.platform_label)
    result = collect(
        source,
        keyword,
        location,
        fetcher=ScraplingFetcher(source.fetcher, headless, network_idle),
        relevance_filter=_is_relevant_job,
        **(url_extra or {}),
    )
    _log_health(result)
    return result


def _log_health(result: CollectionResult) -> None:
    """An empty run is an error -- unless the board itself says there are none."""
    if result.status in {"failed", "broken_cards", "broken_fields"}:
        logger.error("%s %s: %s", result.source, result.status.upper(), result.diagnosis)
    elif result.status == "degraded":
        logger.warning("%s DEGRADED: %s", result.source, result.diagnosis)
    elif result.status == "no_results":
        logger.info("%s: %s", result.source, result.diagnosis)
    else:
        logger.info(
            "%s ok: %d listings, %d relevant, %.1fs",
            result.source,
            result.titles_found,
            len(result.jobs),
            result.duration_seconds,
        )
