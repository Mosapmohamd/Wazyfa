"""Config-driven scraping engine.

One algorithm serves every board. A board is a YAML entry, not a module of
copy-pasted parsing code -- which is how three of the five original scrapers
managed to ship with fatal bugs that nobody noticed (a missing ``import``, and
two functions with no ``return`` statement).

Item 1 -- health is computed and reported. A source that returns nothing is
never treated as a successful run.
Item 3 -- a card that fails to parse is skipped and counted, not allowed to
abort the rest of the page.
Item 11 -- selectors live in config/sources.yaml.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote_plus

import yaml
from lxml import html as lxml_html
from pydantic import BaseModel, Field

from src.scrapers import extraction

CONFIG_PATH = Path(__file__).parent / "config" / "sources.yaml"


class FetcherKind(str, Enum):
    """Not every board needs a browser.

    LinkedIn's guest endpoint returns a plain HTML fragment; paying stealth
    browser cost for it is waste, and one fewer launch is one fewer
    fingerprint.
    """

    STEALTHY = "stealthy"
    STATIC = "static"


class ExtractionMethod(str, Enum):
    NEXT_DATA = "next_data"
    JSON_LD = "json_ld"
    CSS = "css"


class CardSelectors(BaseModel):
    """Candidate lists, tried in order. Boards A/B test their markup."""

    card: list[str]
    title: list[str] = Field(default_factory=list)
    title_link: list[str] = Field(default_factory=list)
    company: list[str] = Field(default_factory=list)
    location: list[str] = Field(default_factory=list)


class NextDataConfig(BaseModel):
    """Where a Next.js board keeps its results and how its fields are named."""

    json_path: str
    fields: dict[str, str]
    link_template: str | None = None


class SourceConfig(BaseModel):
    name: str
    platform_label: str
    enabled: bool = True
    fetcher: FetcherKind = FetcherKind.STEALTHY
    base_url: str
    search_url_template: str
    strip_query_from_links: bool = False
    try_json_ld: bool = True
    # Text the board renders when a search legitimately matches nothing.
    # Without this, "the site has no AI jobs today" is indistinguishable
    # from "our card selector died".
    no_results_markers: list[str] = Field(default_factory=list)
    next_data: NextDataConfig | None = None
    selectors: CardSelectors

    def build_url(self, keyword: str, location: str, start: int = 0, **extra: str) -> str:
        """Item 4: every interpolated value is percent-encoded."""
        return self.search_url_template.format(
            keyword=quote_plus(keyword.strip()),
            location=quote_plus(location.strip()),
            start=start,
            **{k: quote_plus(v) for k, v in extra.items()},
        )


class SourcesFile(BaseModel):
    sources: list[SourceConfig]


def load_sources(path: Path = CONFIG_PATH) -> dict[str, SourceConfig]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {s.name: s for s in SourcesFile.model_validate(raw).sources}


@dataclass(slots=True)
class CollectionResult:
    """Outcome of one source.

    `titles_found` is tracked separately from `jobs` because the two answer
    different questions. `jobs` is what survived the relevance filter, and a
    board whose own search is loose can legitimately yield 30 cards and one
    relevant job. Only `titles_found` tells you whether *extraction* works.
    Conflating them is what made the first version of this report claim
    Indeed's selectors were stale when Indeed had simply returned no matches.
    """

    source: str
    jobs: list[dict[str, str]] = field(default_factory=list)
    cards_seen: int = 0
    titles_found: int = 0
    card_errors: int = 0
    fatal_error: str | None = None
    site_reports_no_results: bool = False
    duration_seconds: float = 0.0

    @property
    def status(self) -> str:
        if self.fatal_error:
            return "failed"
        if self.site_reports_no_results and not self.cards_seen:
            # The board itself said there are no matches. Nothing is broken.
            return "no_results"
        if not self.titles_found and not self.cards_seen:
            return "broken_cards"
        if not self.titles_found:
            return "broken_fields"
        if self.card_errors:
            return "degraded"
        return "ok"

    @property
    def is_healthy(self) -> bool:
        return self.status in {"ok", "no_results"}

    @property
    def diagnosis(self) -> str:
        return {
            "failed": f"fetch failed: {self.fatal_error}",
            "no_results": "the board reports no matching jobs; nothing is broken",
            "broken_cards": (
                "no cards matched -- the `card` selector is stale, or the page "
                "did not render (check the dumped HTML)"
            ),
            "broken_fields": (
                f"{self.cards_seen} cards found but no titles extracted -- "
                "the `title` selector is stale"
            ),
            "degraded": f"{self.card_errors} cards failed to parse",
            "ok": (
                f"{self.titles_found} listings extracted, "
                f"{len(self.jobs)} relevant"
            ),
        }[self.status]


class PageFetcher(Protocol):
    def fetch(self, url: str) -> str: ...


def _extract_html(response: object) -> str:
    """Read raw HTML out of a Scrapling response across library versions.

    This is the only place version-sniffing is permitted. The original code
    did the same guesswork (`getattr(node, "attrib", None) or
    getattr(node, "attrs", {})`) inside the per-card parse loop, five times
    over. Confining it here lets everything downstream be plain lxml, which
    is deterministic and testable without a browser.
    """
    for attribute in ("html_content", "body", "content", "text"):
        value = getattr(response, attribute, None)
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        if isinstance(value, str) and value.strip():
            return value
    rendered = str(response)
    if rendered.strip():
        return rendered
    raise RuntimeError("could not read HTML from the fetcher response")


class ScraplingFetcher:
    def __init__(self, kind: FetcherKind, headless: bool = True, network_idle: bool = True) -> None:
        self.kind = kind
        self.headless = headless
        self.network_idle = network_idle

    def fetch(self, url: str) -> str:
        if self.kind is FetcherKind.STEALTHY:
            from scrapling.fetchers import StealthyFetcher

            response = StealthyFetcher.fetch(
                url, headless=self.headless, network_idle=self.network_idle
            )
        else:
            from scrapling.fetchers import Fetcher

            response = Fetcher.get(url)
        # Item 5: no post-fetch sleep. The response is already materialised;
        # network_idle is what actually waits for async content.
        return _extract_html(response)


def collect(
    source: SourceConfig,
    keyword: str,
    location: str,
    fetcher: PageFetcher,
    relevance_filter=None,
    **url_extra: str,
) -> CollectionResult:
    """Fetch one search page and extract jobs. Never raises."""
    started = time.perf_counter()
    result = CollectionResult(source=source.platform_label)

    if not keyword.strip():
        result.fatal_error = "empty keyword"
        return result

    try:
        page_html = fetcher.fetch(source.build_url(keyword, location, **url_extra))
    except Exception as exc:
        result.fatal_error = f"{type(exc).__name__}: {exc}"
        result.duration_seconds = time.perf_counter() - started
        return result

    lowered = page_html.lower()
    result.site_reports_no_results = any(
        marker.lower() in lowered for marker in source.no_results_markers
    )

    def keep(title: str) -> bool:
        return relevance_filter is None or relevance_filter(keyword, title)

    # --- Every strategy runs, then results are merged ------------------------
    #
    # An earlier version stopped as soon as one strategy produced a title.
    # On Jobzella that meant a single stray JSON-LD posting left over from a
    # 2023 job suppressed the CSS/Next.js path entirely, and a page that said
    # "119 results" was collected as one irrelevant row. Cheap strategies are
    # not authoritative just because they ran first.

    candidates: list[tuple[dict[str, Any], ExtractionMethod]] = []

    if source.next_data:
        for payload in extraction.extract_next_data_postings(
            page_html,
            source.next_data.json_path,
            source.next_data.fields,
            source.next_data.link_template,
        ):
            candidates.append((payload, ExtractionMethod.NEXT_DATA))

    if source.try_json_ld:
        for payload in extraction.extract_json_ld_postings(page_html):
            candidates.append((payload, ExtractionMethod.JSON_LD))

    try:
        document = lxml_html.fromstring(page_html)
    except Exception as exc:
        document = None
        if not candidates:
            result.fatal_error = f"HTML parse failed: {exc}"
            result.duration_seconds = time.perf_counter() - started
            return result

    if document is not None:
        cards = extraction.find_first_matching(document, source.selectors.card)
        result.cards_seen = len(cards)

        for index, card in enumerate(cards):
            # Per-card isolation: one malformed card must not lose the page.
            try:
                candidates.append(
                    (
                        {
                            "title": extraction.select_text(
                                card, source.selectors.title
                            ),
                            "url": extraction.select_attribute(
                                card, source.selectors.title_link
                            ),
                            "company": extraction.select_text(
                                card, source.selectors.company
                            ),
                        },
                        ExtractionMethod.CSS,
                    )
                )
            except Exception:
                result.card_errors += 1

    seen: set[str] = set()
    for payload, method in candidates:
        job = _build(
            source,
            payload.get("title"),
            payload.get("url"),
            payload.get("company"),
            method,
        )
        if job is None:
            continue
        key = f"{job['Title'].lower()}|{job['Company'].lower()}"
        if key in seen:
            continue
        seen.add(key)
        result.titles_found += 1
        if keep(job["Title"]):
            result.jobs.append(job)

    result.duration_seconds = time.perf_counter() - started
    return result


def _build(
    source: SourceConfig,
    title: str | None,
    href: str | None,
    company: str | None,
    method: ExtractionMethod,
) -> dict[str, str] | None:
    """Build the job dict. Keys match the existing API contract."""
    title = extraction.clean_text(title)
    if not title:
        return None

    url = extraction.absolutise(href, source.base_url)
    if url and source.strip_query_from_links:
        url = extraction.strip_query(url)

    return {
        "Platform": source.platform_label,
        "Title": title,
        # Item 10: unknown stays unknown. "N/A" preserves the existing
        # contract with JobListing, but it is now honest rather than a
        # guess scraped off a neighbouring element.
        "Company": extraction.clean_company(company) or "N/A",
        "Link": url or "N/A",
        "extraction_method": method.value,
    }
