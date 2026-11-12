"""Cache inspection endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app.services import cache_service

router = APIRouter()


@router.get(
    "/cache/stats",
    summary="Row counts for all cache tables",
)
def cache_stats() -> dict[str, object]:
    return cache_service.get_stats()
