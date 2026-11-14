"""Backward-compatible shim: the analyzer now lives in the src.skill_gap package."""

from src.skill_gap import (  # noqa: F401
    KEYWORDS,
    _PROMPT_TEMPLATE,
    _external_api_analysis,
    _fallback_analysis,
    _load_llm,
    _nvidia_fallback_analysis,
    analyze_skill_gap,
)

__all__ = [
    "KEYWORDS",
    "_PROMPT_TEMPLATE",
    "_external_api_analysis",
    "_fallback_analysis",
    "_load_llm",
    "_nvidia_fallback_analysis",
    "analyze_skill_gap",
]
