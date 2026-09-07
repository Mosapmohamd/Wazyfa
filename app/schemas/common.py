"""Shared job-tracking schemas."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class JobBase(BaseModel):
    id: str
    job_type: str
    status: JobStatus
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None


def job_record_to_dict(record: Any) -> dict[str, Any]:
    """Convert a JobRecord into fields accepted by the response schemas."""

    return {
        "id": record.id,
        "job_type": record.job_type,
        "status": record.status,
        "created_at": record.created_at,
        "started_at": record.started_at,
        "finished_at": record.finished_at,
        "error": record.error,
    }
