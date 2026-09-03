"""Config-driven CSS extraction.

Item 10 -- the most important behavioural change in this layer.

The original script, when it failed to find a company, looped over every
`<a>` and `<span>` in the card and took the first text that was not the
title and not in a four-word English blacklist. In practice that returns
"Cairo, Egypt", "2 days ago" or "Full Time" and stores it as a company
name with no indication anything went wrong.

Here: if no configured selector matches, the field is None. A missing
field is recoverable and visible. A confidently wrong field is neither.
"""

from __future__ import annotations

from lxml.html import HtmlElement

from job_radar.config.sources import CardSelectors
from job_radar.extraction.normalize import clean_text


def select_text(element: HtmlElement, selectors: list[str]) -> str | None:
    """First non-empty text among the candidate selectors, else None."""
    for selector in selectors:
        try:
            matches = element.cssselect(selector)
        except Exception:
            # An invalid selector in config should not kill the run.
            continue
        for match in matches:
            text = clean_text(match.text_content())
            if text:
                return text
    return None


def select_attribute(
    element: HtmlElement, selectors: list[str], attribute: str = "href"
) -> str | None:
    """First non-empty attribute value among the candidate selectors."""
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


def select_datetime_attribute(
    element: HtmlElement, selectors: list[str]
) -> str | None:
    """`<time datetime="...">` is more parseable than "2 days ago"."""
    value = select_attribute(element, selectors, "datetime")
    if value:
        return value
    return select_text(element, selectors)


def extract_card_fields(
    card: HtmlElement, selectors: CardSelectors
) -> dict[str, str | None]:
    """Extract the raw field set for one card. No inference, no guessing."""
    return {
        "title": select_text(card, selectors.title),
        "href": select_attribute(card, selectors.title_link),
        "company": select_text(card, selectors.company),
        "location": select_text(card, selectors.location),
        "posted_raw": select_datetime_attribute(card, selectors.posted_at),
    }


def find_cards(document: HtmlElement, selectors: CardSelectors) -> list[HtmlElement]:
    """Return cards from the first card selector that matches anything."""
    for selector in selectors.card:
        try:
            cards = document.cssselect(selector)
        except Exception:
            continue
        if cards:
            return cards
    return []
