"""Seniority and Role filtering and Excel export helpers."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import pandas as pd

from src.embedding_model import SmallEmbeddingModel, EmbeddingConfig

logger = logging.getLogger(__name__)

# Configuration for semantic matching
_SEMANTIC_CONFIG = EmbeddingConfig(
    model_name="sentence-transformers/all-MiniLM-L6-v2",
    threshold=0.55,  # Balanced threshold to catch synonyms while avoiding false positives
)
_semantic_model: SmallEmbeddingModel | None = None


def _semantic_rescue(
    target_role: str,
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Recover only role-rejected jobs that are semantically close to the role.
    
    This function uses semantic similarity to rescue jobs that don't match the 
    regex pattern but are semantically similar to the target role.
    
    Args:
        target_role: The target role to match against (e.g., 'Backend', 'AI').
        candidates: List of job dictionaries that were rejected by regex filters.
        
    Returns:
        List of rescued jobs with match metadata added.
    """

    global _semantic_model
    if not candidates or target_role.strip().lower() in {"", "any", "all"}:
        return []

    try:
        if _semantic_model is None:
            _semantic_model = SmallEmbeddingModel(_SEMANTIC_CONFIG)
        
        if not _semantic_model.is_available:
            logger.warning("Semantic model unavailable; keeping strict filter results")
            return []
            
        rescued_jobs = _semantic_model.rescue_jobs(
            target_text=target_role,
            rejected_jobs=candidates,
            match_type="role",
            threshold=_SEMANTIC_CONFIG.threshold,
        )
        return rescued_jobs
        
    except Exception:
        logger.exception("Semantic job matching unavailable; keeping strict filter results")
        return []

SUPPORTED_LEVELS = (
    "Intern",
    "Entry-Level",
    "Junior",
    "Mid-Level",
    "Senior",
    "Lead",
    "Manager",
    "Director",
)

# Terms that immediately disqualify a title for a given level
_EXCLUSION_PATTERNS = {
    "intern": r"\b(senior|sr\.?|lead|manager|head|principal|staff|director|vp|junior|jr\.?|mid|mid[\s-]?level|entry)\b",
    "entry-level": r"\b(senior|sr\.?|lead|manager|head|principal|staff|director|vp|intern|trainee|mid|mid[\s-]?level|junior|jr\.?)\b",
    "junior": r"\b(senior|sr\.?|lead|manager|head|principal|staff|director|vp|intern|trainee|entry|mid|mid[\s-]?level)\b",
    "mid-level": r"\b(senior|sr\.?|lead|manager|head|principal|staff|director|vp|junior|jr\.?|intern|trainee|entry)\b",
    "senior": r"\b(junior|jr\.?|intern|trainee|entry|mid|mid[\s-]?level|lead|manager|head|principal|staff|director|vp)\b",
    "lead": r"\b(junior|jr\.?|intern|trainee|entry|mid|mid[\s-]?level|manager|head|director|vp)\b",
    "manager": r"\b(junior|jr\.?|intern|trainee|entry|mid|mid[\s-]?level|director|vp|head)\b",
    "director": r"\b(junior|jr\.?|intern|trainee|entry|mid|mid[\s-]?level|manager|lead)\b",
}

# Terms that positively prove a title matches a requested level.
_POSITIVE_PATTERNS = {
    "intern": r"\b(intern|internship|trainee|co-op)\b",
    "entry-level": r"\b(entry[- ]?level|entry|graduate|fresh)\b",
    "junior": r"\b(junior|jr\.?|entry[- ]?level|graduate|associate)\b",
    "mid-level": r"\b(mid[- ]?level|intermediate)\b",
    "senior": r"\b(senior|sr\.?)\b",
    "lead": r"\b(lead|principal|staff)\b",
    "manager": r"\b(manager|mgr|head of)\b",
    "director": r"\b(director|dir|head of|vp|vice president|chief)\b",
}

# Terms that positively identify a specific job domain/role.
_ROLE_PATTERNS = {
    "backend": r"\b(backend|back-end|back end)\b",
    "frontend": r"\b(frontend|front-end|front end)\b",
    "fullstack": r"\b(fullstack|full-stack|full stack)\b",
    "ai": r"\b(ai|artificial intelligence|machine learning|ml|deep learning|nlp|computer vision)\b",
    "data": r"\b(data\s?(scientist|engineer|analyst))\b",
    "software": r"\b(software|swe)\b",
}


def filter_jobs(
    jobs: list[dict[str, Any]],
    target_level: str = "Junior",
    target_role: str = "Any",
) -> list[dict[str, Any]]:
    """Keep useful listings while excluding clearly conflicting seniority and unrelated roles.

    Also filters out job titles that have fewer than 2 words.
    """

    # 1. إعداد فلتر الأقدمية (Seniority Setup)
    level_key = target_level.lower().strip()
    exclude_regex = None
    positive_regex = None
    
    if level_key not in {"", "any", "any level", "all", "all levels"}:
        exclude_pattern = _EXCLUSION_PATTERNS.get(level_key)
        exclude_regex = re.compile(exclude_pattern, re.IGNORECASE) if exclude_pattern else None
        
        positive_pattern = _POSITIVE_PATTERNS.get(level_key)
        positive_regex = re.compile(positive_pattern, re.IGNORECASE) if positive_pattern else None

    # 2. إعداد فلتر التخصص (Role Setup)
    role_key = target_role.lower().strip()
    role_regex = None
    if role_key not in {"", "any", "all"}:
        # إذا لم يكن التخصص موجوداً في القاموس، استخدم الكلمة المدخلة كما هي كـ Regex
        role_pattern = _ROLE_PATTERNS.get(role_key, rf"\b{re.escape(target_role)}\b")
        role_regex = re.compile(role_pattern, re.IGNORECASE)

    filtered = []
    role_rejected = []
    conflict_count = 0
    short_title_count = 0
    role_miss_count = 0

    for job in jobs:
        title = str(job.get("Title", "")).strip()

        # أ. فحص التخصص (Strict Role Check)
        if role_regex and not role_regex.search(title):
            job["seniority_match"] = "wrong_role"
            role_miss_count += 1
            words = [word for word in title.split() if word]
            if len(words) < 2:
                job["seniority_match"] = "invalid_length"
                short_title_count += 1
            elif exclude_regex and exclude_regex.search(title):
                job["seniority_match"] = "conflict"
                conflict_count += 1
            else:
                role_rejected.append(job)
            continue

        # ب. فحص عدد الكلمات (Word count check)
        words = [w for w in title.split() if w]
        if len(words) < 2:
            job["seniority_match"] = "invalid_length"
            short_title_count += 1
            continue

        # ج. فحص الاستبعاد للأقدمية (Seniority Exclusion check)
        if exclude_regex and exclude_regex.search(title):
            job["seniority_match"] = "conflict"
            conflict_count += 1
            continue

        # د. فحص المطابقة الإيجابية للأقدمية (Seniority Positive match check)
        if positive_regex and positive_regex.search(title):
            job["seniority_match"] = "explicit"
        elif level_key in {"", "any", "any level", "all", "all levels"}:
            job["seniority_match"] = "explicit"
        else:
            job["seniority_match"] = "unknown"

        filtered.append(job)

    rescued = _semantic_rescue(target_role, role_rejected)
    filtered.extend(rescued)

    logger.info(
        "Classified jobs for %s (%s role): %d explicit, %d unknown, %d conflict, %d wrong role, %d too short; %d retained of %d listings",
        target_level,
        target_role,
        sum(job.get("seniority_match") == "explicit" for job in filtered),
        sum(job.get("seniority_match") == "unknown" for job in filtered),
        conflict_count,
        role_miss_count,
        short_title_count,
        len(filtered),
        len(jobs),
    )
    return filtered


def export_to_excel(
    jobs: list[dict[str, Any]],
    output_path: str | Path,
) -> Path | None:
    """Export normalized job fields to an Excel file."""

    if not jobs:
        logger.warning("No jobs to export")
        return None

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(jobs)
    for column in ("Platform", "Title", "Company", "Link"):
        if column not in frame:
            frame[column] = "N/A"
    
    if "seniority_match" not in frame:
        frame["seniority_match"] = "explicit"
        
    frame.to_excel(path, index=False)
    logger.info("Exported %d jobs to %s", len(frame), path)
    return path


def filter_and_export(
    jobs: list[dict[str, Any]],
    target_level: str = "Junior",
    target_role: str = "Any",
    output_path: str | Path = "Filtered_Jobs.xlsx",
) -> list[dict[str, Any]]:
    """Filter jobs by seniority and role, export them, and return the filtered list."""

    filtered = filter_jobs(jobs, target_level, target_role)
    export_to_excel(filtered, output_path)
    return filtered