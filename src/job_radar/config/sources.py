"""Source configuration.

Item 11: every selector, URL template and quirk lives in config/sources.yaml.
Adding Bayt or Forasna is a YAML entry, not a new 40-line block of code.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from urllib.parse import quote_plus

import yaml
from pydantic import BaseModel, Field


class FetcherKind(str, Enum):
    """Not every source needs a full browser.

    LinkedIn's guest endpoint returns a plain HTML fragment, so paying the
    cost of a stealth browser for it is pure waste.
    """

    STEALTHY = "stealthy"
    STATIC = "static"


class CardSelectors(BaseModel):
    """Candidate selector lists, tried in order until one yields text.

    Lists (not single strings) because job boards A/B test their markup and
    ship two card variants at once.
    """

    card: list[str]
    title: list[str] = Field(default_factory=list)
    title_link: list[str] = Field(default_factory=list)
    company: list[str] = Field(default_factory=list)
    location: list[str] = Field(default_factory=list)
    posted_at: list[str] = Field(default_factory=list)


class SourceConfig(BaseModel):
    name: str
    enabled: bool = True
    fetcher: FetcherKind = FetcherKind.STEALTHY
    base_url: str
    search_url_template: str
    strip_query_from_links: bool = False

    # Item 8: prefer structured data when the page carries it.
    try_json_ld: bool = True

    # Item 1: below this, the run is reported as degraded/empty, not "success".
    min_expected_results: int = 1

    selectors: CardSelectors

    def build_url(self, keyword: str, location: str, start: int = 0) -> str:
        """Item 4: every user-supplied value is percent-encoded.

        The old f-string broke on '&', '+' and Arabic keywords.
        """
        return self.search_url_template.format(
            keyword=quote_plus(keyword),
            location=quote_plus(location),
            start=start,
        )


class SourcesFile(BaseModel):
    sources: list[SourceConfig]


def load_sources(path: Path) -> list[SourceConfig]:
    """Load and validate sources.yaml. Invalid config fails loudly at startup."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return SourcesFile.model_validate(raw).sources
