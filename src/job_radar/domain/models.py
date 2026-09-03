"""Core domain models.

Item 12: typed Pydantic models instead of untyped dicts.
Item 2:  empty strings normalise to None so downstream `if not company`
         checks actually work.
Item 6:  no character stripping (`-`) is ever applied to names.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from job_radar.extraction.normalize import clean_text


class ExtractionMethod(str, Enum):
    """How a field set was obtained. Used by the health check."""

    JSON_LD = "json_ld"
    MICRODATA = "microdata"
    CSS = "css"


class JobPosting(BaseModel):
    """A single job advert, normalised across platforms."""

    model_config = ConfigDict(str_strip_whitespace=False, frozen=True)

    platform: str
    title: str
    url: str | None = None
    company: str | None = None
    location: str | None = None
    posted_at: datetime | None = None

    extraction_method: ExtractionMethod
    collected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @field_validator("title", "company", "location", "url", mode="before")
    @classmethod
    def _clean(cls, value: object) -> str | None:
        """Collapse whitespace; turn blanks into None. Never strips chars."""
        if value is None:
            return None
        return clean_text(str(value))

    @field_validator("title")
    @classmethod
    def _title_required(cls, value: str | None) -> str:
        if not value:
            raise ValueError("title is required and cannot be blank")
        return value

    @property
    def fingerprint(self) -> str:
        """Stable id for dedup/persistence (used from stage 2 onwards)."""
        parts = [
            self.platform.lower(),
            (self.title or "").lower(),
            (self.company or "").lower(),
        ]
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]

    @property
    def is_complete(self) -> bool:
        return bool(self.title and self.company and self.url)


class CollectionResult(BaseModel):
    """Outcome of running one collector. Carries failures, not just data.

    Item 1: a run that returns nothing is not a success. `status` makes the
    difference between "no jobs today" and "our selectors are dead" explicit.
    Item 3: `card_errors` counts per-card failures that were swallowed so the
    rest of the page could still be parsed.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    source: str
    jobs: list[JobPosting] = Field(default_factory=list)
    cards_seen: int = 0
    card_errors: int = 0
    fatal_error: str | None = None
    min_expected: int = 1
    duration_seconds: float = 0.0

    @property
    def status(self) -> str:
        if self.fatal_error:
            return "failed"
        if not self.jobs:
            return "empty"
        if len(self.jobs) < self.min_expected:
            return "degraded"
        if self.card_errors:
            return "degraded"
        return "ok"

    @property
    def is_healthy(self) -> bool:
        return self.status == "ok"

    @property
    def method_breakdown(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for job in self.jobs:
            counts[job.extraction_method.value] = (
                counts.get(job.extraction_method.value, 0) + 1
            )
        return counts
