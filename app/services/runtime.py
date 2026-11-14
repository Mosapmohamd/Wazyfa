"""Process-wide singletons."""

from __future__ import annotations

from app.core.config import api_settings
from app.services.job_store import JobStore

job_store = JobStore(history_limit=api_settings.job_history_limit)
