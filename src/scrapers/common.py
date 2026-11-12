"""Shared helpers for job-board scrapers: relevance filtering and deduplication."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_GENERIC_ROLE_WORDS = {
    "developer", "engineer", "analyst", "scientist", "specialist", "manager",
    "architect", "consultant", "designer", "administrator", "professional",
    "assistant", "associate", "coordinator", "executive", "officer", "lead",
    "director", "head", "intern", "trainee", "advisor", "agent", "technician",
}
_TERM_SYNONYMS = (
    {"ai", "ml", "machine learning", "artificial intelligence", "deep learning"},
    {"backend", "back-end", "back end"},
    {"frontend", "front-end", "front end"},
    {"fullstack", "full-stack", "full stack"},
    {"hr", "human resources"},
    {"qa", "quality assurance", "testing"},
    {"accounting", "accountant"},
)
_INDEED_DOMAINS = {
    "argentina": "ar.indeed.com", "australia": "au.indeed.com",
    "brazil": "br.indeed.com", "canada": "ca.indeed.com",
    "egypt": "eg.indeed.com", "france": "fr.indeed.com",
    "germany": "de.indeed.com", "india": "in.indeed.com",
    "italy": "it.indeed.com", "japan": "jp.indeed.com",
    "mexico": "mx.indeed.com", "netherlands": "nl.indeed.com",
    "spain": "es.indeed.com", "switzerland": "ch.indeed.com",
    "united kingdom": "uk.indeed.com", "uk": "uk.indeed.com",
    "united states": "www.indeed.com", "usa": "www.indeed.com",
}
_BAYT_COUNTRY_SLUGS = {
    "egypt": "egypt", "uae": "uae", "united arab emirates": "uae",
    "saudi arabia": "saudi-arabia", "qatar": "qatar", "kuwait": "kuwait",
    "bahrain": "bahrain", "oman": "oman", "jordan": "jordan",
    "lebanon": "lebanon", "morocco": "morocco", "tunisia": "tunisia",
    "algeria": "algeria", "pakistan": "pakistan", "india": "india",
}


def _country_name(location: str) -> str:
    """Return the country part of a city/country location string when known."""

    value = re.sub(r"\s+", " ", location.strip().lower())
    for country in sorted(set(_INDEED_DOMAINS) | set(_BAYT_COUNTRY_SLUGS), key=len, reverse=True):
        if country in value:
            return country
    return value


def _bayt_country_slug(location: str) -> str:
    country = _country_name(location)
    return _BAYT_COUNTRY_SLUGS.get(country, re.sub(r"[^a-z0-9]+", "-", country).strip("-"))


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", value.lower()) if len(token) > 1}


def _canonical_role_text(value: str) -> str:
    """Normalize common compound role spellings before comparing titles."""

    value = re.sub(r"\bback[\s-]+end\b", "backend", value, flags=re.IGNORECASE)
    value = re.sub(r"\bfront[\s-]+end\b", "frontend", value, flags=re.IGNORECASE)
    value = re.sub(r"\bfull[\s-]+stack\b", "fullstack", value, flags=re.IGNORECASE)
    value = re.sub(r"\bmachine[\s-]+learning\b", "ml", value, flags=re.IGNORECASE)
    value = re.sub(r"\bartificial[\s-]+intelligence\b", "ai", value, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", value.strip().lower())



def _contains_term(text: str, term: str) -> bool:
    """Match a synonym on word boundaries, never as a substring.

    The previous implementation used `term in text`, which for two-letter
    terms like "ai" and "ml" matched inside ordinary words. Searching for
    "AI Engineer" therefore returned "Car Detailing Technician",
    "Retail Manager", "Email Marketing Specialist", "Maintenance Engineer",
    "Training Coordinator" and "HTML Developer" -- every one of them a false
    positive that then flowed into the description fetcher, the embedding
    model and the skill-gap analysis.
    """

    return re.search(rf"\b{re.escape(term)}\b", text) is not None


def _is_relevant_job(keyword: str, title: str) -> bool:
    """Keep titles matching the requested role family, not just generic job words."""

    keyword_text = _canonical_role_text(keyword)
    title_text = _canonical_role_text(title)
    if not keyword_text or not title_text:
        return False
    if keyword_text in title_text:
        return True

    keyword_tokens = _tokens(keyword_text)
    title_tokens = _tokens(title_text)
    if not keyword_tokens or not title_tokens:
        return False

    # A generic overlap such as "engineer" is insufficient on its own.
    distinctive = keyword_tokens - _GENERIC_ROLE_WORDS
    direct_match = distinctive & title_tokens
    synonym_match = any(
        _contains_term(keyword_text, term_a) and _contains_term(title_text, term_b)
        for group in _TERM_SYNONYMS
        for term_a in group
        for term_b in group
    )
    if distinctive:
        return bool(direct_match or synonym_match)
    return bool(keyword_tokens & title_tokens)


def _deduplicate_jobs(jobs: list[dict[str, str]]) -> list[dict[str, str]]:
    """Remove repeated listings returned by multiple sources or pagination."""

    unique: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for job in jobs:
        title = re.sub(r"\s+", " ", str(job.get("Title", "")).strip())
        company = re.sub(r"\s+", " ", str(job.get("Company", "")).strip())
        link = str(job.get("Link", "")).split("?")[0].rstrip("/").lower()
        key = (link, f"{title.lower()}|{company.lower()}") if link not in {"", "n/a"} else ("", f"{title.lower()}|{company.lower()}")
        if key == ("", "|") or key in seen:
            continue
        seen.add(key)
        job["Title"] = title
        job["Company"] = company or "N/A"
        unique.append(job)
    return unique


def annotate_cross_platform_duplicates(
    jobs: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Mark the same role posted on several boards -- do not collapse it.

    Item 15, with the agreed behaviour: duplicates stay as separate rows.
    Collapsing them would pick one application link and silently discard the
    others, and the two postings are genuinely different listings.

    Adds two keys:
      duplicate_group     shared id for listings judged to be the same role
      also_on             the other platforms carrying it
    """

    from src.job_ledger import cross_platform_key

    groups: dict[str, list[dict[str, str]]] = {}
    for job in jobs:
        key = cross_platform_key(job)
        if key:
            groups.setdefault(key, []).append(job)

    group_id = 0
    for key, members in groups.items():
        platforms = {str(m.get("Platform", "")) for m in members}
        if len(platforms) < 2:
            continue
        group_id += 1
        for member in members:
            own = str(member.get("Platform", ""))
            member["duplicate_group"] = f"g{group_id}"
            member["also_on"] = sorted(platforms - {own})

    if group_id:
        logger.info("Marked %d role(s) as appearing on multiple boards", group_id)
    return jobs
