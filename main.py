"""Command-line controller for the AI Job Skill Gap Analyzer.

Thin CLI wrapper over the shared pipeline service; the CLI shares the same
orchestration and run-scoped artifacts as the API.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from app.core.exceptions import AppError
from app.services.pipeline_service import execute_pipeline
from config import settings
from src.job_filter import SUPPORTED_LEVELS


def configure_logging() -> None:
    """Configure console and file logging once for the pipeline."""

    settings.ensure_dirs()
    root_logger = logging.getLogger()
    if root_logger.handlers:
        return

    root_logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    file_handler = logging.FileHandler(
        settings.data_dir / "pipeline_errors.log",
        encoding="utf-8",
    )
    stream_handler = logging.StreamHandler(sys.stdout)
    file_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(stream_handler)


configure_logging()
logger = logging.getLogger(__name__)


def run_pipeline(
    keyword: str = settings.keyword,
    cv_path: str | Path = settings.cv_path,
    target_level: str = settings.target_level,
    target_role: str = settings.target_role,
) -> str:
    """Run the complete CV-to-skill-gap pipeline and return report text."""

    settings.ensure_dirs()
    logger.info(
        "Starting pipeline: keyword=%r level=%r CV=%s",
        keyword,
        target_level,
        cv_path,
    )

    try:
        result = execute_pipeline(
            cv_path=cv_path,
            keyword=keyword,
            target_level=target_level,
            target_role=target_role,
            location=settings.location,
        )
    except AppError as exc:
        logger.error("Pipeline stopped: %s", exc.detail)
        return ""

    logger.info("Pipeline completed; report saved to %s", result["report_path"])
    return result["report"]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI Job Skill Gap Analyzer")
    parser.add_argument("--keyword", default=settings.keyword, help="Job search keyword")
    parser.add_argument("--cv", default=str(settings.cv_path), help="Path to the CV PDF")
    parser.add_argument(
        "--level",
        default=settings.target_level,
        choices=SUPPORTED_LEVELS,
        help="Target seniority level",
    )
    parser.add_argument(
        "--role",
        default=settings.target_role,
        help="Target specific role (e.g., backend, frontend, ai)",
    )
    return parser


if __name__ == "__main__":
    arguments = _build_parser().parse_args()
    run_pipeline(
        keyword=arguments.keyword,
        cv_path=Path(arguments.cv),
        target_level=arguments.level,
        target_role=arguments.role,
    )