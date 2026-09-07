"""Extraction primitives shared by every job-board scraper.

Ported from the stage 0/1 rewrite. Three rules are enforced here:

* Item 2 -- blank text becomes ``None``, never ``""``, so ``if not company``
  is a reliable check everywhere downstream.
* Item 6 -- nothing strips characters from names. The old
  ``.replace("-", "")`` turned "E-finance" into "Efinance".
* Item 10 -- a field that cannot be found stays ``None``. It is never
  inferred from neighbouring text.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Iterator
from urllib.parse import urljoin, urlsplit, urlunsplit

from lxml import html as lxml_html
from lxml.html import HtmlElement

_WHITESPACE = re.compile(r"\s+")
_INVISIBLE = re.compile(r"[\u200b\u200c\u200d\u2060\ufeff]")
# Separator characters left dangling at the edges of a company cell.
_EDGE_SEPARATORS = re.compile(r"^[\s\-\u2013\u2014|\u00b7,:;/]+|[\s\-\u2013\u2014|\u00b7,:;/]+$")


# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------
def clean_text(raw: str | None) -> str | None:
    """Collapse whitespace and trim. Returns None when nothing is left."""
    if raw is None:
        return None
    text = _INVISIBLE.sub("", str(raw)).replace("\xa0", " ")
    return _WHITESPACE.sub(" ", text).strip() or None


def clean_company(raw: str | None) -> str | None:
    """Clean a company name and trim separator characters at the edges.

    Boards often render the company cell as "The-Code - " or "Acme | Cairo",
    leaving a dangling separator once the sibling text is dropped. Only the
    edges are trimmed: internal hyphens are preserved, so "E-finance" and
    "Al-Ahly" survive intact. This is the opposite of the old
    `.replace("-", "")`, which removed every hyphen in the string.
    """
    text = clean_text(raw)
    if not text:
        return None
    text = _EDGE_SEPARATORS.sub("", text)
    return clean_text(text)


def absolutise(href: str | None, base_url: str) -> str | None:
    """Resolve a possibly-relative href against the board's base URL."""
    href = clean_text(href)
    if not href or href.startswith(("mailto:", "javascript:", "#")):
        return None
    return urljoin(base_url, href)


def strip_query(url: str | None) -> str | None:
    """Drop query and fragment. LinkedIn appends per-session tracking params."""
    if not url:
        return None
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


# ---------------------------------------------------------------------------
# JSON-LD  (item 8)
# ---------------------------------------------------------------------------
def _iter_json_objects(node: Any) -> Iterator[dict[str, Any]]:
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _iter_json_objects(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_json_objects(item)


def _is_job_posting(obj: dict[str, Any]) -> bool:
    raw = obj.get("@type")
    types = raw if isinstance(raw, list) else [raw]
    return any(isinstance(t, str) and t.lower() == "jobposting" for t in types)


def _parse_date(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(text[:10], fmt)
            except ValueError:
                continue
    return None


def _company_name(obj: dict[str, Any]) -> str | None:
    org = obj.get("hiringOrganization")
    if isinstance(org, dict):
        name = org.get("name")
        return name if isinstance(name, str) else None
    return org if isinstance(org, str) else None


def _location_name(obj: dict[str, Any]) -> str | None:
    loc = obj.get("jobLocation")
    if isinstance(loc, list):
        loc = loc[0] if loc else None
    if isinstance(loc, dict):
        address = loc.get("address")
        if isinstance(address, dict):
            parts = [
                address.get("addressLocality"),
                address.get("addressRegion"),
                address.get("addressCountry"),
            ]
            return ", ".join(p for p in parts if isinstance(p, str) and p) or None
        if isinstance(address, str):
            return address
    return None


def extract_json_ld_postings(page_html: str) -> list[dict[str, Any]]:
    """Return normalised field dicts for every schema.org JobPosting found.

    Caveat: JSON-LD is reliably present on job *detail* pages and only
    sometimes on search-result pages, so this is the first link in a chain,
    not a replacement for CSS on listings.
    """
    try:
        document = lxml_html.fromstring(page_html)
    except Exception:
        return []

    found: list[dict[str, Any]] = []
    for script in document.cssselect('script[type="application/ld+json"]'):
        payload = (script.text_content() or "").strip()
        if not payload:
            continue
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue  # malformed blocks are common; not worth failing over
        for obj in _iter_json_objects(data):
            if _is_job_posting(obj):
                found.append(
                    {
                        "title": obj.get("title"),
                        "company": _company_name(obj),
                        "location": _location_name(obj),
                        "url": obj.get("url") or obj.get("@id"),
                        "posted_at": _parse_date(obj.get("datePosted")),
                    }
                )
    return found


# ---------------------------------------------------------------------------
# CSS  (items 10, 11)
# ---------------------------------------------------------------------------
def select_text(element: HtmlElement, selectors: list[str]) -> str | None:
    """First non-empty text among candidate selectors, else None.

    Item 10: there is deliberately no "search the whole card for something
    that looks like a company" fallback. The previous one returned
    "Cairo, Egypt", "2 days ago" and "Full Time" as company names.
    """
    for selector in selectors:
        try:
            matches = element.cssselect(selector)
        except Exception:
            continue  # a bad selector in config must not kill the run
        for match in matches:
            text = clean_text(match.text_content())
            if text:
                return text
    return None


def select_attribute(
    element: HtmlElement, selectors: list[str], attribute: str = "href"
) -> str | None:
    for selector in selectors:
        try:
            matches = element.cssselect(selector)
        except Exception:
            continue
        for match in matches:
            value = clean_text(match.get(attribute))
            if value:
                return value
    return None


def find_first_matching(
    document: HtmlElement, selectors: list[str]
) -> list[HtmlElement]:
    """Cards from the first selector that matches anything."""
    for selector in selectors:
        try:
            cards = document.cssselect(selector)
        except Exception:
            continue
        if cards:
            return cards
    return []


# ---------------------------------------------------------------------------
# __NEXT_DATA__  -- Next.js boards embed their results as JSON
# ---------------------------------------------------------------------------
_NEXT_DATA = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S
)


def _dig(obj: Any, dotted: str) -> Any:
    """Follow a dotted path such as "props.pageProps.jobs" or "company.title"."""
    for part in dotted.split("."):
        if isinstance(obj, dict):
            obj = obj.get(part)
        elif isinstance(obj, list) and part.isdigit():
            obj = obj[int(part)] if int(part) < len(obj) else None
        else:
            return None
        if obj is None:
            return None
    return obj


def extract_next_data_postings(
    page_html: str,
    json_path: str,
    fields: dict[str, str],
    link_template: str | None = None,
) -> list[dict[str, Any]]:
    """Read job rows out of a Next.js page's embedded JSON payload.

    Far more stable than CSS for these boards: the field names come from the
    site's own API contract rather than from generated class names like
    `css-1238myt`, which change on every build.
    """
    match = _NEXT_DATA.search(page_html)
    if not match:
        return []
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []

    rows = _dig(payload, json_path)
    if not isinstance(rows, list):
        return []

    postings: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        record = {key: _dig(row, path) for key, path in fields.items()}
        if link_template:
            try:
                record["url"] = link_template.format(**{
                    k: v for k, v in record.items() if v is not None
                })
            except (KeyError, IndexError):
                record["url"] = None
        postings.append(
            {
                "title": record.get("title"),
                "company": record.get("company"),
                "location": record.get("location"),
                "url": record.get("url"),
                "posted_at": None,
            }
        )
    return postings
