"""Transport layer.

Design decision: Scrapling is used ONLY to fetch. All parsing is done with
lxml. Reason -- Scrapling's element API has shifted between versions
(`.attrib` vs `.attrs`, `.text` semantics), which is exactly what forced the
scattered `hasattr()` checks in the original script. By converting to raw
HTML at the boundary, that variance is contained in this one file and the
whole extraction layer becomes deterministic and unit-testable without a
browser.

Item 5: there is no post-fetch `sleep()`. The response is already fully
materialised; `network_idle=True` is what actually waits for async content.
"""

from __future__ import annotations

from typing import Protocol

from loguru import logger

from job_radar.config.sources import FetcherKind


class FetchError(RuntimeError):
    """Raised when a page could not be retrieved at all."""


class PageFetcher(Protocol):
    """Anything that can turn a URL into HTML. Fakes satisfy this in tests."""

    def fetch(self, url: str) -> str: ...


def _extract_html(response: object) -> str:
    """Pull raw HTML out of a Scrapling response across library versions.

    This is the *only* place version-sniffing is allowed. It is acceptable
    here because it is one isolated adapter with a clear failure mode --
    unlike the original code, where the same guesswork sat inside the
    per-card parsing loop.
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
    raise FetchError("could not read HTML from the fetcher response")


class ScraplingFetcher:
    """Real fetcher backed by Scrapling."""

    def __init__(self, kind: FetcherKind, timeout_ms: int = 30_000) -> None:
        self._kind = kind
        self._timeout_ms = timeout_ms

    def fetch(self, url: str) -> str:
        logger.debug("fetching url={} mode={}", url, self._kind.value)
        try:
            if self._kind is FetcherKind.STEALTHY:
                from scrapling.fetchers import StealthyFetcher

                response = StealthyFetcher.fetch(
                    url,
                    headless=True,
                    network_idle=True,
                    timeout=self._timeout_ms,
                )
            else:
                from scrapling.fetchers import Fetcher

                response = Fetcher.get(url, timeout=self._timeout_ms // 1000)
        except ImportError as exc:  # pragma: no cover
            raise FetchError(f"scrapling import failed: {exc}") from exc
        except Exception as exc:
            raise FetchError(f"fetch failed for {url}: {exc}") from exc

        html = _extract_html(response)
        logger.debug("fetched url={} bytes={}", url, len(html))
        return html


def build_fetcher(kind: FetcherKind, timeout_ms: int = 30_000) -> PageFetcher:
    return ScraplingFetcher(kind, timeout_ms)
