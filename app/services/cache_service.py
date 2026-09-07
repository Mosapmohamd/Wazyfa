"""Thin wrapper over the existing SQLite CacheManager singleton."""

from __future__ import annotations

from typing import Any

from src.cache_manager import system_cache


def get_stats() -> dict[str, Any]:
    return system_cache.get_stats()


def get_cached_search(keyword: str, location: str) -> list[dict[str, Any]] | None:
    return system_cache.get_cached_search(keyword, location)
