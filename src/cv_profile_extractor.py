"""Heuristic CV profile extraction for CV-driven job search."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

ROLE_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("AI Engineer", ("ai engineer", "artificial intelligence engineer", "ai developer")),
    ("Machine Learning Engineer", ("machine learning engineer", "ml engineer", "machine learning")),
    ("Data Scientist", ("data scientist", "data science")),
    ("Data Engineer", ("data engineer", "data engineering")),
    ("Backend Engineer", ("backend engineer", "backend developer", "back-end developer")),
    ("Software Engineer", ("software engineer", "software developer")),
    ("DevOps Engineer", ("devops engineer", "devops", "site reliability engineer")),
    ("Cloud Engineer", ("cloud engineer", "cloud developer")),
    ("NLP Engineer", ("nlp engineer", "natural language processing")),
    ("Computer Vision Engineer", ("computer vision engineer", "computer vision")),
)

LEVEL_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Intern", ("intern", "internship")),
    ("Entry-Level", ("entry level", "entry-level", "graduate", "new graduate")),
    ("Junior", ("junior", "jr.", "jr ")),
    ("Mid-Level", ("mid-level", "mid level")),
    ("Senior", ("senior", "sr.", "sr ")),
    ("Lead", ("lead engineer", "team lead", "technical lead")),
    ("Manager", ("engineering manager", "technical manager", "manager")),
    ("Director", ("director", "head of")),
)

SKILL_TERMS = (
    "python", "pytorch", "tensorflow", "docker", "aws", "azure", "gcp", "nlp",
    "natural language processing", "rag", "llm", "transformers", "machine learning",
    "deep learning", "computer vision", "opencv", "kubernetes", "spark", "sql",
    "mongodb", "postgresql", "redis", "fastapi", "flask", "django", "rest",
    "graphql", "kafka", "airflow", "mlflow", "wandb", "git", "jenkins", "terraform",
    "langchain", "llamaindex", "huggingface", "openai", "scikit-learn", "pandas",
    "numpy", "scipy", "matplotlib", "seaborn", "tableau", "power bi", "excel",
)


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _count_signals(text: str, signals: tuple[str, ...]) -> int:
    """Count signal occurrences safely using word boundaries."""
    count = 0
    for signal in signals:
        # Use \b for word boundaries to avoid 'intern' matching 'printern'
        # For signals that end with punctuation, re.escape handles it correctly.
        pattern = r"\b" + re.escape(signal) + r"\b"
        if re.search(pattern, text):
            # Multi-word signals are more specific and get higher weight
            count += 2 if " " in signal else 1
    return count


def extract_cv_profile(cv_text: str) -> dict[str, Any]:
    """Infer a role, seniority, and skills from extracted CV text."""

    normalized = _normalized(cv_text)
    role_scores: Counter[str] = Counter()
    for role, signals in ROLE_PATTERNS:
        score = _count_signals(normalized, signals)
        if score > 0:
            role_scores[role] = score

    level_scores: Counter[str] = Counter()
    for level, signals in LEVEL_PATTERNS:
        score = _count_signals(normalized, signals)
        if score > 0:
            level_scores[level] = score

    # most_common(1) resolves ties deterministically by insertion order
    role = role_scores.most_common(1)[0][0] if role_scores else "AI Engineer"
    target_level = level_scores.most_common(1)[0][0] if level_scores else "Junior"
    
    # Use word boundaries for skills too
    skills = [
        skill for skill in SKILL_TERMS 
        if re.search(r"\b" + re.escape(skill) + r"\b", normalized)
    ]

    return {
        "role": role,
        "target_level": target_level,
        "skills": skills,
        "matched_signals": {
            "role": dict(role_scores),
            "seniority": dict(level_scores),
        },
    }