"""Text normalisation.

Item 6: the old `.replace('-', '')` mangled real names ("E-finance",
"Al-Ahly"). Nothing here removes characters -- it only collapses
whitespace and trims.

Item 2: blank results become None rather than "", so `if not company`
is a reliable check everywhere downstream.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlsplit, urlunsplit

_WHITESPACE = re.compile(r"\s+")

# Zero-width and non-breaking characters that job boards inject into markup.
_INVISIBLE = re.compile(r"[\u200b\u200c\u200d\u2060\ufeff]")


def clean_text(raw: str | None) -> str | None:
    """Collapse all whitespace runs into single spaces and trim.

    Returns None for input that is empty after cleaning.
    """
    if raw is None:
        return None
    text = _INVISIBLE.sub("", raw)
    text = text.replace("\xa0", " ")
    text = _WHITESPACE.sub(" ", text).strip()
    return text or None


def absolutise(href: str | None, base_url: str) -> str | None:
    """Resolve a possibly-relative href against the source's base URL."""
    href = clean_text(href)
    if not href:
        return None
    if href.startswith(("mailto:", "javascript:", "#")):
        return None
    return urljoin(base_url, href)


def strip_query(url: str | None) -> str | None:
    """Drop query string and fragment -- LinkedIn appends tracking params."""
    if not url:
        return None
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
