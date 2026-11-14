"""CV-only analysis: review a CV without market data.

Returns detected skills, strengths, missing information, recommended roles,
and estimated seniority. Reuses the existing LLM model loader from
skill_gap_analyzer to avoid loading a second model.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.core.exceptions import CVExtractionError
from config import settings as project_settings
from src.cv_extractor import extract_cv_text
from src.cv_profile_extractor import extract_cv_profile

logger = logging.getLogger(__name__)

_CV_DIRECT_PROMPT = """\
Role: Expert technical recruiter and career advisor.
Task: Perform a thorough CV-only review. Do NOT compare against any market data.

INPUT
[CV]: {cv_text}

RULES
1. Ground every claim in the CV text. Do not invent experience, dates, or metrics.
2. Identify technical skills, soft skills, and tools/frameworks mentioned.
3. Assess strengths based on evidence in the CV.
4. Identify missing information that a recruiter would expect (quantified achievements,
   project links, GitHub, clear timeline).
5. Recommend suitable job roles based on the candidate's profile.
6. Estimate seniority level from experience depth and project complexity.

OUTPUT
Return only valid JSON in this structure:
{
  "detected_skills": {
    "technical": [],
    "soft": [],
    "tools": []
  },
  "strengths": [],
  "missing_information": [],
  "recommended_roles": [],
  "estimated_seniority": "",
  "full_review": ""
}"""


def _deterministic_cv_review(cv_text: str, profile: dict[str, Any]) -> str:
    """Build a basic CV review from the heuristic profile when no LLM is available."""

    skills = profile.get("skills", [])
    role = profile.get("role", "Unknown")
    level = profile.get("target_level", "Unknown")

    report = {
        "detected_skills": {
            "technical": [s for s in skills if s not in ("git", "excel", "docker", "kubernetes", "jenkins", "terraform")],
            "soft": [],
            "tools": [s for s in skills if s in ("git", "excel", "docker", "kubernetes", "jenkins", "terraform")],
        },
        "strengths": (
            [f"Detected experience with {', '.join(skills[:5])}"]
            if skills else ["No specific skills detected via keyword matching"]
        ),
        "missing_information": [
            "Quantified achievements (metrics, impact numbers)",
            "Project links (GitHub, portfolio)",
            "Clear timeline of experience",
        ],
        "recommended_roles": [role],
        "estimated_seniority": level,
        "full_review": (
            f"The CV suggests a {level} {role} profile. "
            f"Detected skills include: {', '.join(skills) if skills else 'none explicitly matched'}. "
            "Consider adding quantified achievements, project links, and a clear experience timeline "
            "to strengthen the CV for recruiter review."
        ),
    }
    return json.dumps(report, ensure_ascii=False)


def _external_api_cv_review(cv_text: str) -> str | None:
    """Use the configured external LLM provider for CV review if explicitly allowed."""
    
    if not project_settings.allow_external_ai:
        return None
    
    try:
        from src.llm_client import get_llm_client
        client = get_llm_client(project_settings)
        
        if not client.is_available():
            logger.warning("External LLM client not available")
            return None
        
        prompt = _CV_DIRECT_PROMPT.replace("{cv_text}", cv_text[:15000])
        messages = [
            {
                "role": "system",
                "content": "Return only valid JSON based solely on the provided CV.",
            },
            {"role": "user", "content": prompt},
        ]
        
        response = client.chat_completion(
            messages=messages,
            temperature=0.1,
            max_tokens=2560,
        )
        return response
    except Exception:
        logger.exception("External API CV review failed")
        return None


def _nvidia_cv_review(cv_text: str) -> str | None:
    """Use NVIDIA NIM for CV-only review if explicitly allowed (legacy function)."""
    
    if not project_settings.allow_external_ai or not project_settings.nvidia_api_key:
        return None

    try:
        from openai import OpenAI
    except ImportError:
        logger.warning("openai package not installed; skipping NVIDIA CV review")
        return None

    prompt = _CV_DIRECT_PROMPT.replace("{cv_text}", cv_text[:15000])

    try:
        client = OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=project_settings.nvidia_api_key,
            timeout=60.0,
        )
        completion = client.chat.completions.create(
            model=project_settings.nvidia_fallback_model,
            messages=[
                {
                    "role": "system",
                    "content": "Return only valid JSON based solely on the provided CV.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=2560,
        )
        return completion.choices[0].message.content or None
    except Exception:
        logger.exception("NVIDIA CV review failed")
        return None


def _local_llm_cv_review(cv_text: str) -> str | None:
    """Use the local LLM for CV-only review, reusing the existing model loader."""

    try:
        from src.skill_gap_analyzer import _load_llm
        import torch
    except Exception:
        return None

    try:
        pipe = _load_llm(project_settings.llm_model, project_settings.use_4bit)
        prompt = _CV_DIRECT_PROMPT.replace("{cv_text}", cv_text[:15000])

        messages = [
            {"role": "system", "content": "You are a precise technical recruiter. Return only valid JSON."},
            {"role": "user", "content": prompt},
        ]

        if hasattr(pipe.tokenizer, "apply_chat_template"):
            encoded = pipe.tokenizer.apply_chat_template(
                messages,
                return_tensors="pt",
                add_generation_prompt=True,
                return_dict=True,
            )
            input_ids = encoded["input_ids"].to(pipe.model.device)
            attention_mask = encoded.get("attention_mask")
            if attention_mask is not None:
                attention_mask = attention_mask.to(pipe.model.device)
        else:
            encoded = pipe.tokenizer(prompt, return_tensors="pt")
            input_ids = encoded.input_ids.to(pipe.model.device)
            attention_mask = encoded.attention_mask.to(pipe.model.device)

        with torch.no_grad():
            outputs = pipe.model.generate(
                input_ids,
                attention_mask=attention_mask,
                max_new_tokens=project_settings.llm_max_new_tokens,
                do_sample=True,
                temperature=0.1,
                pad_token_id=pipe.tokenizer.eos_token_id,
            )

        generated = outputs[0][input_ids.shape[-1]:]
        result = pipe.tokenizer.decode(generated, skip_special_tokens=True).strip()
        return result or None
    except Exception:
        logger.exception("Local LLM CV review failed")
        return None


def execute_cv_direct_analysis(*, cv_path: str | Path, upload_id: str = "") -> dict[str, Any]:
    """Analyze a CV without market data.

    Returns detected skills, strengths, missing information, recommended roles,
    and estimated seniority. LLM review uses the configured external provider
    (via LLM_PROVIDER env var) with fallback to local model → deterministic analysis.
    """

    cv_text = extract_cv_text(cv_path)
    if not cv_text:
        raise CVExtractionError(
            "Could not extract text from the CV. It may be image-only or corrupted."
        )

    profile = extract_cv_profile(cv_text)

    # LLM review: Try external API first (if enabled), then local, then deterministic
    review_json: str | None = None

    # Try external API (configured provider: nvidia/openai/anthropic/google/azure/custom)
    review_json = _external_api_cv_review(cv_text)
    
    # Fallback to local LLM
    if review_json is None:
        review_json = _local_llm_cv_review(cv_text)
    
    # Final fallback to NVIDIA legacy (for backward compatibility)
    if review_json is None:
        review_json = _nvidia_cv_review(cv_text)

    # Deterministic fallback
    if review_json is None:
        logger.info("Using deterministic CV review (no LLM available)")
        review_json = _deterministic_cv_review(cv_text, profile)

    return {
        "upload_id": upload_id,
        "role": profile["role"],
        "target_level": profile["target_level"],
        "skills": profile["skills"],
        "matched_signals": profile["matched_signals"],
        "extracted_chars": len(cv_text),
        "review": review_json,
    }
