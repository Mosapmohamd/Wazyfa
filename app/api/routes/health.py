"""Health and readiness endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Response, status

from app.core.config import api_settings
from src.cache_manager import system_cache

logger = logging.getLogger(__name__)

router = APIRouter()

_REQUIRED_CHECKS = ("cache_database", "pdf_extraction", "scraping_engine")


def _check_cache_database() -> tuple[bool, str]:
    try:
        stats = system_cache.get_stats()
        return True, stats.get("database", "ok")
    except Exception:
        logger.exception("Cache database check failed")
        return False, "unavailable"


def _check_pdf_extraction() -> tuple[bool, str]:
    try:
        import fitz  # noqa: F401  (PyMuPDF)
        return True, "ok"
    except Exception:
        return False, "PyMuPDF not installed"


def _check_scraping_engine() -> tuple[bool, str]:
    try:
        from scrapling import StealthyFetcher  # noqa: F401
        return True, "ok"
    except Exception:
        return False, "scrapling not installed"


def _check_llm_backend() -> tuple[bool, str]:
    try:
        import torch  # noqa: F401
        return True, "ok"
    except Exception:
        # Not a hard failure: NVIDIA NIM / keyword fallback paths still exist.
        return False, "torch not installed (local LLM unavailable; fallbacks apply)"


@router.get("/health", summary="Liveness check")
def health() -> dict[str, str]:
    return {"status": "ok", "app": api_settings.app_name}


@router.get("/ready", summary="Readiness check (cache DB, PDF, scraping engine)")
def ready(response: Response) -> dict[str, object]:
    checks = {
        "cache_database": _check_cache_database(),
        "pdf_extraction": _check_pdf_extraction(),
        "scraping_engine": _check_scraping_engine(),
        "llm_backend": _check_llm_backend(),
    }
    ready_state = all(checks[name][0] for name in _REQUIRED_CHECKS)
    if not ready_state:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ready" if ready_state else "not_ready",
        "checks": {
            name: {"status": "ok" if ok else "error", "detail": detail}
            for name, (ok, detail) in checks.items()
        },
    }
