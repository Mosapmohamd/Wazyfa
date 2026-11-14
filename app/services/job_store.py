"""Thread-safe in-memory background-job registry."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.schemas.common import JobStatus


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class JobRecord:
    id: str
    job_type: str
    params: dict[str, Any] = field(default_factory=dict)
    status: JobStatus = JobStatus.PENDING
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class JobStore:
    """Keeps job records in memory. Jobs are lost on process restart."""

    def __init__(self, history_limit: int = 200) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = threading.Lock()
        self._history_limit = history_limit

    def create(self, job_type: str, params: dict[str, Any]) -> JobRecord:
        record = JobRecord(id=uuid.uuid4().hex, job_type=job_type, params=params)
        with self._lock:
            self._jobs[record.id] = record
            self._trim()
        return record

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def mark_running(self, job_id: str) -> None:
        with self._lock:
            record = self._jobs.get(job_id)
            if record:
                record.status = JobStatus.RUNNING
                record.started_at = _now()

    def complete(self, job_id: str, result: dict[str, Any]) -> None:
        with self._lock:
            record = self._jobs.get(job_id)
            if record:
                record.status = JobStatus.COMPLETED
                record.result = result
                record.finished_at = _now()

    def fail(self, job_id: str, error: str) -> None:
        with self._lock:
            record = self._jobs.get(job_id)
            if record:
                record.status = JobStatus.FAILED
                record.error = error
                record.finished_at = _now()

    def clear(self) -> None:
        with self._lock:
            self._jobs.clear()

    def _trim(self) -> None:
        if len(self._jobs) <= self._history_limit:
            return
        oldest = sorted(self._jobs.values(), key=lambda r: r.created_at)
        for record in oldest[: len(self._jobs) - self._history_limit]:
            self._jobs.pop(record.id, None)
