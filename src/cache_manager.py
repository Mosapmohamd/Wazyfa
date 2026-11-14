"""SQLite-backed cache for job searches, descriptions, summaries, and embeddings."""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class CacheManager:
    """Manage the project cache through a shared SQLite connection."""

    def __init__(self, db_path: str | Path = "data/system_cache.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            timeout=30,
        )
        self._lock = threading.RLock()
        self._create_tables()

    def _create_tables(self) -> None:
        """Create all cache tables if they do not already exist."""

        with self._lock:
            cursor = self.conn.cursor()
            cursor.executescript(
                """
                CREATE TABLE IF NOT EXISTS job_descriptions (
                    url_hash TEXT PRIMARY KEY,
                    description TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS market_summaries (
                    query_hash TEXT PRIMARY KEY,
                    summary TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS skill_embeddings (
                    skill_name TEXT PRIMARY KEY,
                    vector_data TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS job_searches (
                    query_hash TEXT PRIMARY KEY,
                    jobs_json TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                );
                """
            )
            self.conn.commit()

    @staticmethod
    def _generate_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _search_key(keyword: str, location: str) -> str:
        return f"{keyword.strip().lower()}_{location.strip().lower()}"

    @staticmethod
    def _summary_key(keyword: str, level: str, location: str) -> str:
        return (
            f"{keyword.strip().lower()}_{level.strip().lower()}_"
            f"{location.strip().lower()}"
        )

    def get_cached_search(
        self,
        keyword: str,
        location: str,
        max_hours: int = 24,
        empty_max_hours: int = 1,
    ) -> list[dict[str, Any]] | None:
        """Return a recent job search, or ``None`` when it is missing/expired.
        
        Uses a shorter TTL (empty_max_hours) for empty results to avoid 
        long-term caching of temporary scraping failures.
        """

        query_hash = self._generate_hash(self._search_key(keyword, location))
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT jobs_json, timestamp FROM job_searches WHERE query_hash = ?",
                (query_hash,),
            )
            result = cursor.fetchone()

        if not result:
            return None

        jobs_json, timestamp = result
        try:
            last_scrape = datetime.fromisoformat(timestamp)
        except ValueError:
            logger.warning("Ignoring cache entry with invalid timestamp: %s", timestamp)
            return None

        try:
            jobs = json.loads(jobs_json)
        except json.JSONDecodeError:
            logger.warning("Ignoring malformed cached jobs for %s", keyword)
            return None

        # Apply different TTLs based on whether the cache is empty
        time_delta = datetime.now() - last_scrape
        if not jobs:
            if time_delta >= timedelta(hours=empty_max_hours):
                return None
        else:
            if time_delta >= timedelta(hours=max_hours):
                return None

        logger.info("Cache hit for job search: %s in %s", keyword, location)
        return jobs

    def set_cached_search(
        self,
        keyword: str,
        location: str,
        jobs: list[dict[str, Any]],
    ) -> None:
        """Store the latest job search result (including empty lists)."""

        query_hash = self._generate_hash(self._search_key(keyword, location))
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO job_searches "
                "(query_hash, jobs_json, timestamp) VALUES (?, ?, ?)",
                (query_hash, json.dumps(jobs, ensure_ascii=False), datetime.now().isoformat()),
            )
            self.conn.commit()

    def get_job_description(self, url: str) -> str | None:
        url_hash = self._generate_hash(url)
        with self._lock:
            row = self.conn.execute(
                "SELECT description FROM job_descriptions WHERE url_hash = ?",
                (url_hash,),
            ).fetchone()
        return row[0] if row else None

    def set_job_description(self, url: str, description: str) -> None:
        url_hash = self._generate_hash(url)
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO job_descriptions (url_hash, description) VALUES (?, ?)",
                (url_hash, description),
            )
            self.conn.commit()

    def get_market_summary(self, keyword: str, level: str, location: str) -> str | None:
        query_hash = self._generate_hash(self._summary_key(keyword, level, location))
        with self._lock:
            row = self.conn.execute(
                "SELECT summary FROM market_summaries WHERE query_hash = ?",
                (query_hash,),
            ).fetchone()
        return row[0] if row else None

    def set_market_summary(
        self,
        keyword: str,
        level: str,
        location: str,
        summary: str,
    ) -> None:
        query_hash = self._generate_hash(self._summary_key(keyword, level, location))
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO market_summaries (query_hash, summary) VALUES (?, ?)",
                (query_hash, summary),
            )
            self.conn.commit()

    def get_skill_embedding(self, skill_name: str) -> list[float] | None:
        skill_clean = skill_name.lower().strip()
        with self._lock:
            row = self.conn.execute(
                "SELECT vector_data FROM skill_embeddings WHERE skill_name = ?",
                (skill_clean,),
            ).fetchone()
        if not row:
            return None
        try:
            return json.loads(row[0])
        except json.JSONDecodeError:
            logger.warning("Ignoring malformed embedding for %s", skill_name)
            return None

    def set_skill_embedding(self, skill_name: str, vector: list[float]) -> None:
        skill_clean = skill_name.lower().strip()
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO skill_embeddings (skill_name, vector_data) VALUES (?, ?)",
                (skill_clean, json.dumps(vector)),
            )
            self.conn.commit()

    def get_stats(self) -> dict[str, Any]:
        """Return row counts for all cache tables."""

        table_names = (
            "job_descriptions",
            "market_summaries",
            "skill_embeddings",
            "job_searches",
        )
        with self._lock:
            counts = {
                table: int(
                    self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                )
                for table in table_names
            }
        return {
            "database": str(self.db_path),
            "exists": self.db_path.exists(),
            "tables": counts,
        }

    def close(self) -> None:
        """Close the SQLite connection."""

        with self._lock:
            self.conn.close()


system_cache = CacheManager()