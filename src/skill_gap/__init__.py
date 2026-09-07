"""Skill-gap analysis package (prompts, local LLM, external providers, fallback)."""

from src.skill_gap.analyzer import analyze_skill_gap
from src.skill_gap.external import _external_api_analysis, _nvidia_fallback_analysis
from src.skill_gap.fallback import _fallback_analysis
from src.skill_gap.local_llm import _load_llm
from src.skill_gap.prompts import KEYWORDS, _PROMPT_TEMPLATE

__all__ = [
    "KEYWORDS",
    "_PROMPT_TEMPLATE",
    "_external_api_analysis",
    "_fallback_analysis",
    "_load_llm",
    "_nvidia_fallback_analysis",
    "analyze_skill_gap",
]
