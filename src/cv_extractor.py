"""PDF text extraction utilities."""

from __future__ import annotations

import logging
import re
from pathlib import Path

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

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
        pattern = r"\b" + re.escape(signal) + r"\b"
        if re.search(pattern, text):
            count += 2 if " " in signal else 1
    return count


def _resolve_inference(scores: Counter[str], default: str) -> tuple[str, float, bool, list[str]]:
    """Determine the best match, confidence, and tie information."""

    if not scores:
        # BUG-010 Fix: Explicitly flag when a default is used instead of an inferred value
        return default, 0.0, True, []

    top_items = scores.most_common()
    top_role, top_score = top_items[0]

    # Find all items that tie with the top score
    tied = sorted([role for role, score in top_items if score == top_score])

    # Calculate confidence
    if len(top_items) == 1:
        confidence = 1.0
    elif top_score > top_items[1][1]:
        confidence = top_score / (top_score + top_items[1][1])
    else:
        # Exact tie
        confidence = 0.5

    # Sort tied candidates alphabetically for deterministic behavior regardless of dict insertion order
    selected = tied[0]

    return selected, round(confidence, 2), False, tied


def extract_cv_text(pdf_path: str | Path) -> str | None:
    """Extract normalized text from every page of a PDF file."""

    path = Path(pdf_path)
    if not path.exists():
        logger.error("CV file not found: %s", path)
        return None

    try:
        with fitz.open(str(path)) as document:
            raw_text = "\n".join(page.get_text("text") for page in document)
    except Exception:
        logger.exception("Failed to extract text from CV: %s", path)
        return None

    clean_text = re.sub(r"\n{2,}", "\n", raw_text).strip()
    if not clean_text:
        logger.warning("CV contains no extractable text and may be image-only: %s", path)
        return None

    logger.info("Extracted %d characters from %s", len(clean_text), path.name)
    return clean_text