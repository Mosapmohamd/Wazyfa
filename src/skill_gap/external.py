"""External LLM-provider analysis paths (opt-in via ALLOW_EXTERNAL_AI)."""

from __future__ import annotations

import logging

from src.skill_gap.fallback import _fallback_analysis
from src.skill_gap.prompts import _PROMPT_TEMPLATE

logger = logging.getLogger(__name__)


def _external_api_analysis(cv_text: str, market_summary: str) -> str | None:
    """Use the configured external LLM provider for skill-gap analysis if explicitly allowed."""
    
    from config import settings
    
    # BUG-007 Fix: Require explicit opt-in before sending CV data externally
    if not settings.allow_external_ai:
        return None
    
    try:
        from src.llm_client import get_llm_client
        client = get_llm_client(settings)
        
        if not client.is_available():
            logger.warning("External LLM client not available")
            return None
        
        prompt = (
            _PROMPT_TEMPLATE
            .replace("{market_summary}", market_summary)
            .replace("{cv_text}", cv_text)
        )
        
        messages = [
            {
                "role": "system",
                "content": "Return only valid JSON and use only the supplied evidence.",
            },
            {"role": "user", "content": prompt},
        ]
        
        response = client.chat_completion(
            messages=messages,
            temperature=0.1,
            max_tokens=2560,
        )
        return response or None
    except Exception:
        logger.exception("External API skill-gap analysis failed")
        return None


def _nvidia_fallback_analysis(cv_text: str, market_summary: str) -> str:
    """Use NVIDIA NIM when configured and explicitly allowed, otherwise use deterministic analysis (legacy)."""

    from config import settings

    # BUG-007 Fix: Require explicit opt-in before sending CV data externally
    if not settings.allow_external_ai or not settings.nvidia_api_key:
        return _fallback_analysis(cv_text, market_summary)

    try:
        from openai import OpenAI
    except ImportError:
        logger.warning("The optional openai package is not installed")
        return _fallback_analysis(cv_text, market_summary)

    prompt = (
        _PROMPT_TEMPLATE
        .replace("{market_summary}", market_summary)
        .replace("{cv_text}", cv_text)
    )
    try:
        client = OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=settings.nvidia_api_key,
            timeout=60.0, # Add a timeout
        )
        completion = client.chat.completions.create(
            model=settings.nvidia_fallback_model,
            messages=[
                {
                    "role": "system",
                    "content": "Return only valid JSON and use only the supplied evidence.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=2560,
        )
        return completion.choices[0].message.content or _fallback_analysis(cv_text, market_summary)
    except Exception:
        logger.exception("NVIDIA fallback analysis failed")
        return _fallback_analysis(cv_text, market_summary)
