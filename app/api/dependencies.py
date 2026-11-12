"""Dependency providers (also useful for test overrides)."""

from __future__ import annotations

from app.services.cv_service import UploadRegistry, upload_registry
from app.services.job_store import JobStore
from app.services.runtime import job_store


def get_job_store() -> JobStore:
    return job_store


def get_upload_registry() -> UploadRegistry:
    return upload_registry
