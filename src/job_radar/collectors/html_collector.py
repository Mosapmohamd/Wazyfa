"""One generic collector, configured per source.

Item 11: there is no WuzzufCollector and no LinkedInCollector. Both are the
same algorithm with different YAML. Adding Bayt costs zero lines here.

Item 13: this class collects and returns data. It never prints. Rendering
lives in job_radar.reporting.
"""

from __future__ import annotations

import time
from datetime import datetime

from loguru import logger
from lxml import html as lxml_html

from job_radar.config.sources import SourceConfig
from job_radar.domain.models import CollectionResult, ExtractionMethod, JobPosting
from job_radar.extraction import css as css_extractor
from job_radar.extraction import jsonld
from job_radar.extraction.normalize import absolutise, clean_text, strip_query
from job_radar.fetching.fetcher import FetchError, PageFetcher


class HtmlSearchCollector:
    """Fetch a search page, then extract jobs via JSON-LD, falling back to CSS."""

    def __init__(self, source: SourceConfig, fetcher: PageFetcher) -> None:
        self.source = source
        self._fetcher = fetcher

    def collect(self, keyword: str, location: str) -> CollectionResult:
        started = time.perf_counter()
        url = self.source.build_url(keyword, location)
        result = CollectionResult(
            source=self.source.name,
            min_expected=self.source.min_expected_results,
        )

        try:
            page_html = self._fetcher.fetch(url)
        except FetchError as exc:
            result.fatal_error = str(exc)
            result.duration_seconds = time.perf_counter() - started
            return result

        # --- Path 1: structured data (item 8) -------------------------------
        if self.source.try_json_ld:
            for payload in jsonld.extract_job_postings(page_html):
                job = self._build_job(
                    title=payload.get("title"),
                    href=payload.get("url"),
                    company=payload.get("company"),
                    location_text=payload.get("location"),
                    posted_at=payload.get("posted_at"),
                    method=ExtractionMethod.JSON_LD,
                )
                if job:
                    result.jobs.append(job)
            if result.jobs:
                logger.debug(
                    "source={} json-ld yielded {} jobs",
                    self.source.name,
                    len(result.jobs),
                )

        # --- Path 2: configured CSS ----------------------------------------
        if not result.jobs:
            self._collect_via_css(page_html, result)

        result.duration_seconds = time.perf_counter() - started
        return result

    def _collect_via_css(self, page_html: str, result: CollectionResult) -> None:
        try:
            document = lxml_html.fromstring(page_html)
        except Exception as exc:
            result.fatal_error = f"HTML parse failed: {exc}"
            return

        cards = css_extractor.find_cards(document, self.source.selectors)
        result.cards_seen = len(cards)

        for index, card in enumerate(cards):
            # Item 3: per-card isolation. One malformed card used to abort
            # the whole platform mid-loop.
            try:
                fields = css_extractor.extract_card_fields(
                    card, self.source.selectors
                )
                job = self._build_job(
                    title=fields["title"],
                    href=fields["href"],
                    company=fields["company"],
                    location_text=fields["location"],
                    posted_at=None,
                    method=ExtractionMethod.CSS,
                )
                if job:
                    result.jobs.append(job)
            except Exception as exc:
                result.card_errors += 1
                logger.warning(
                    "source={} card={} skipped: {}", self.source.name, index, exc
                )

    def _build_job(
        self,
        *,
        title: str | None,
        href: str | None,
        company: str | None,
        location_text: str | None,
        posted_at: datetime | None,
        method: ExtractionMethod,
    ) -> JobPosting | None:
        title = clean_text(title)
        if not title:
            return None

        url = absolutise(href, self.source.base_url)
        if url and self.source.strip_query_from_links:
            url = strip_query(url)

        # Item 10: company stays None when unknown. No guessing.
        return JobPosting(
            platform=self.source.name,
            title=title,
            url=url,
            company=clean_text(company),
            location=clean_text(location_text),
            posted_at=posted_at,
            extraction_method=method,
        )
