"""Stage 2 -- a persistent ledger of every job ever seen.

This is deliberately NOT the existing CacheManager. The cache answers
"what did search X return recently, so I can skip re-scraping". It expires,
it is keyed by query, and it cannot answer the question that actually matters
day to day:

    "which of these have I not seen before?"

The ledger answers that. It never expires, it is keyed by the job rather than
the query, and it records when each listing was first and last observed.

Items 14 (SQLite + stable fingerprint) and 16 (new since last run).
"""

from __future__ import annotations

import logging
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)

_WHITESPACE = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^a-z0-9\s]")

# Words that carry no identity, so "Senior AI Engineer (Remote)" and
# "Senior AI Engineer - Remote" produce the same fingerprint.
_NOISE_WORDS = {
    "remote", "hybrid", "onsite", "on", "site", "full", "part", "time",
    "contract", "freelance", "urgent", "hiring", "now", "job", "vacancy",
    "opportunity", "new", "immediate", "wfh", "m", "f", "d",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalise_for_matching(value: str | None) -> str:
    """Lowercase, strip punctuation and noise words, sort remaining tokens.

    Token sorting means "AI Engineer, Senior" and "Senior AI Engineer" match.
    """
    if not value:
        return ""
    text = _NON_ALNUM.sub(" ", str(value).lower())
    tokens = [t for t in _WHITESPACE.split(text) if t and t not in _NOISE_WORDS]
    return " ".join(sorted(tokens))


def fingerprint(job: dict[str, Any]) -> str:
    """Identity of a listing: normalised title + company + platform.

    Platform is included on purpose. Per the agreed behaviour, the same role
    posted on two boards stays as two rows -- they are two listings with two
    application links, and collapsing them would silently discard one.
    """
    import hashlib

    parts = [
        normalise_for_matching(job.get("Title")),
        normalise_for_matching(job.get("Company")),
        str(job.get("Platform", "")).strip().lower(),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:20]


# A company we failed to identify must never be used to group listings.
# Two unrelated "AI Engineer" posts with an unknown company are not the same
# job, and treating them as duplicates would hide one of them.
_UNKNOWN_COMPANY = {"", "n/a", "na", "none", "unknown", "-", "confidential"}


def is_unknown_company(value: str | None) -> bool:
    if value is None:
        return True
    return _WHITESPACE.sub(" ", str(value)).strip().lower() in _UNKNOWN_COMPANY


def cross_platform_key(job: dict[str, Any]) -> str:
    """Identity of a *role*, ignoring which board it came from.

    Returns "" when the job cannot be safely grouped, which callers treat as
    "no group". Note that comparing the *normalised* company against "n/a"
    does not work: normalisation strips punctuation and sorts tokens, so
    "N/A" becomes "a n". The check therefore runs on the raw value.
    """
    title = normalise_for_matching(job.get("Title"))
    company_raw = job.get("Company")
    if not title or is_unknown_company(company_raw):
        return ""
    company = normalise_for_matching(company_raw)
    if not company:
        return ""
    return f"{title}|{company}"


class JobLedger:
    """Append-only record of observed listings, backed by SQLite."""

    def __init__(self, db_path: str | Path = "data/system_cache.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._create_tables()

    def _create_tables(self) -> None:
        with self._lock:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS seen_jobs (
                    fingerprint     TEXT PRIMARY KEY,
                    title           TEXT NOT NULL,
                    company         TEXT,
                    platform        TEXT NOT NULL,
                    link            TEXT,
                    role_key        TEXT,
                    first_seen_at   TEXT NOT NULL,
                    last_seen_at    TEXT NOT NULL,
                    times_seen      INTEGER NOT NULL DEFAULT 1
                );
                CREATE INDEX IF NOT EXISTS idx_seen_jobs_first
                    ON seen_jobs(first_seen_at);
                CREATE INDEX IF NOT EXISTS idx_seen_jobs_role
                    ON seen_jobs(role_key);
                """
            )
            self.conn.commit()

    # ------------------------------------------------------------------
    def annotate(self, jobs: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        """Tag each job with `is_new` / `first_seen_at`, then record it.

        `is_new` is True only the first time a fingerprint is ever observed.
        Called once per run, after deduplication within each source.
        """
        jobs = list(jobs)
        if not jobs:
            return jobs

        fingerprints = [fingerprint(job) for job in jobs]
        now = _now()

        with self._lock:
            placeholders = ",".join("?" * len(fingerprints))
            rows = self.conn.execute(
                f"SELECT fingerprint, first_seen_at FROM seen_jobs "  # noqa: S608
                f"WHERE fingerprint IN ({placeholders})",
                fingerprints,
            ).fetchall()
            known = {row["fingerprint"]: row["first_seen_at"] for row in rows}

            for job, fp in zip(jobs, fingerprints, strict=True):
                job["fingerprint"] = fp
                job["is_new"] = fp not in known
                job["first_seen_at"] = known.get(fp, now)

                self.conn.execute(
                    """
                    INSERT INTO seen_jobs
                        (fingerprint, title, company, platform, link,
                         role_key, first_seen_at, last_seen_at, times_seen)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                    ON CONFLICT(fingerprint) DO UPDATE SET
                        last_seen_at = excluded.last_seen_at,
                        times_seen   = times_seen + 1,
                        link         = COALESCE(NULLIF(excluded.link, 'N/A'), link)
                    """,
                    (
                        fp,
                        str(job.get("Title", "")),
                        str(job.get("Company", "")),
                        str(job.get("Platform", "")),
                        str(job.get("Link", "")),
                        cross_platform_key(job),
                        now,
                        now,
                    ),
                )
            self.conn.commit()

        new_count = sum(1 for job in jobs if job["is_new"])
        logger.info("Ledger: %d/%d listings are new", new_count, len(jobs))
        return jobs

    def new_only(self, jobs: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        return [job for job in jobs if job.get("is_new")]

    def stats(self) -> dict[str, int]:
        with self._lock:
            row = self.conn.execute(
                "SELECT COUNT(*) AS total, COUNT(DISTINCT role_key) AS roles "
                "FROM seen_jobs"
            ).fetchone()
        return {"total_listings": row["total"], "distinct_roles": row["roles"]}

    def close(self) -> None:
        with self._lock:
            self.conn.close()


job_ledger = JobLedger()
