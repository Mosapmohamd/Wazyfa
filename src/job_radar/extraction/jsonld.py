"""schema.org/JobPosting extraction from JSON-LD.

Item 8. Caveat worth stating plainly: JSON-LD is reliably present on job
*detail* pages, and only sometimes on search-result pages. So this is not a
drop-in replacement for CSS on listings -- it is the first link in a chain.
When a source does emit it, these fields survive redesigns that break every
CSS selector on the page.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Iterator

from lxml import html as lxml_html


def _iter_json_objects(node: Any) -> Iterator[dict[str, Any]]:
    """Walk arbitrarily nested JSON-LD (@graph, arrays, nested objects)."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _iter_json_objects(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_json_objects(item)


def _is_job_posting(obj: dict[str, Any]) -> bool:
    raw_type = obj.get("@type")
    types = raw_type if isinstance(raw_type, list) else [raw_type]
    return any(
        isinstance(t, str) and t.lower() == "jobposting" for t in types
    )


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
    if isinstance(org, str):
        return org
    return None


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
            joined = ", ".join(p for p in parts if isinstance(p, str) and p)
            return joined or None
        if isinstance(address, str):
            return address
    return None


def extract_job_postings(page_html: str) -> list[dict[str, Any]]:
    """Return normalised field dicts for every JobPosting found in the page."""
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
            # Malformed blocks are common and are not worth failing over.
            continue

        for obj in _iter_json_objects(data):
            if not _is_job_posting(obj):
                continue
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
