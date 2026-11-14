"""Executes blocking service functions in a worker thread, tracked by JobStore."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from app.core.exceptions import AppError
from app.services.runtime import job_store

logger = logging.getLogger(__name__)


async def run_job(job_id: str, fn: Callable[..., dict[str, Any]], **kwargs: Any) -> None:
    """Run a blocking function off the event loop and record the outcome."""

    job_store.mark_running(job_id)
    try:
        result = await asyncio.to_thread(fn, **kwargs)
        job_store.complete(job_id, result)
        logger.info("Job %s completed", job_id)
    except AppError as exc:
        logger.warning("Job %s failed: %s", job_id, exc.detail)
        job_store.fail(job_id, exc.detail)
    except Exception:
        logger.exception("Job %s failed unexpectedly", job_id)
        job_store.fail(job_id, "Internal processing failure")
