"""Run every enabled collector and judge the health of the run.

Item 1 is implemented here and it is the single most valuable change in this
stage. The original script printed a success banner even when it had scraped
absolutely nothing, so a selector break was indistinguishable from a quiet
day on the job market. Now:

  * a source returning zero results is logged at ERROR, not celebrated
  * a source returning fewer than `min_expected_results` is DEGRADED
  * the run carries an exit code, so cron / systemd can alert on it
"""

from __future__ import annotations

from dataclasses import dataclass, field

from loguru import logger

from job_radar.collectors.html_collector import HtmlSearchCollector
from job_radar.config.sources import SourceConfig
from job_radar.domain.models import CollectionResult, JobPosting
from job_radar.fetching.fetcher import build_fetcher


@dataclass(slots=True)
class RunReport:
    keyword: str
    location: str
    results: list[CollectionResult] = field(default_factory=list)

    @property
    def jobs(self) -> list[JobPosting]:
        return [job for result in self.results for job in result.jobs]

    @property
    def failed_sources(self) -> list[str]:
        return [r.source for r in self.results if r.status == "failed"]

    @property
    def empty_sources(self) -> list[str]:
        return [r.source for r in self.results if r.status == "empty"]

    @property
    def degraded_sources(self) -> list[str]:
        return [r.source for r in self.results if r.status == "degraded"]

    @property
    def exit_code(self) -> int:
        """0 = all good, 1 = degraded, 2 = something is broken."""
        if self.failed_sources or self.empty_sources:
            return 2
        if self.degraded_sources:
            return 1
        return 0


def run(
    sources: list[SourceConfig], keyword: str, location: str
) -> RunReport:
    report = RunReport(keyword=keyword, location=location)

    for source in sources:
        if not source.enabled:
            logger.info("source={} skipped (disabled)", source.name)
            continue

        collector = HtmlSearchCollector(source, build_fetcher(source.fetcher))
        result = collector.collect(keyword, location)
        report.results.append(result)
        _log_health(result)

    return report


def _log_health(result: CollectionResult) -> None:
    """Turn a result into an honest log line."""
    if result.status == "failed":
        logger.error(
            "source={} FAILED after {:.1f}s: {}",
            result.source,
            result.duration_seconds,
            result.fatal_error,
        )
        return

    if result.status == "empty":
        logger.error(
            "source={} returned 0 jobs from {} cards -- selectors are likely "
            "broken, or the site changed its markup. This is NOT a successful run.",
            result.source,
            result.cards_seen,
        )
        return

    if result.status == "degraded":
        logger.warning(
            "source={} degraded: {} jobs (expected >= {}), {} cards skipped",
            result.source,
            len(result.jobs),
            result.min_expected,
            result.card_errors,
        )
        return

    logger.info(
        "source={} ok: {} jobs in {:.1f}s via {}",
        result.source,
        len(result.jobs),
        result.duration_seconds,
        result.method_breakdown,
    )
