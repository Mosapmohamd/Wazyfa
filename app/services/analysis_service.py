"""Independent analysis stages: description fetch, market summary, gap analysis.

Each stage can be called independently or chained. The gap-analysis
function orchestrates all three but is triggered by a separate endpoint
so the user sees job listings *before* committing to analysis.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.core.exceptions import AppError, CVExtractionError
from app.services.run_service import run_service
from config import settings as project_settings
from src.cv_extractor import extract_cv_text
from src.description_fetcher import export_enriched, fetch_descriptions
from src.job_filter import filter_jobs
from src.market_summarizer import summarize_market, unload_summarizer
from src.skill_gap_analyzer import analyze_skill_gap

logger = logging.getLogger(__name__)


def execute_analysis(
    *,
    cv_path: str | Path,
    jobs: list[dict[str, Any]],
    keyword: str,
    target_level: str | None = None,
    target_role: str | None = None,
    location: str | None = None,
    cv_text: str | None = None,
) -> dict[str, Any]:
    """Run the gap-analysis chain: filter → fetch descriptions → summarize → analyze.

    This is the *analysis-only* path — jobs already exist from a prior search.
    `cv_text` may be passed by callers (e.g. the full pipeline) that have
    already extracted the CV, avoiding a second PDF parse.
    """

    location = location or project_settings.location
    run = run_service.create_run(
        "gap_analysis",
        {"keyword": keyword, "target_level": target_level, "location": location},
    )

    # 1. Extract CV text (reuse pre-extracted text when provided)
    if cv_text is None:
        cv_text = extract_cv_text(cv_path)
    if not cv_text:
        raise CVExtractionError(
            "Could not extract text from the CV. It may be image-only or corrupted."
        )

    # 2. Filter by seniority if requested
    filtered_jobs = jobs
    if target_level or target_role:
        filtered_jobs = filter_jobs(
            jobs,
            target_level or "Any",
            target_role or "Any",
        )
        if not filtered_jobs:
            raise AppError(
                f"No jobs matched target level {target_level!r}.",
                status_code=422,
            )

    # 3. Fetch descriptions (isolated process + run-specific checkpoint)
    enriched_jobs = fetch_descriptions(
        filtered_jobs,
        headless=project_settings.headless,
        network_idle=project_settings.network_idle,
        min_delay=project_settings.min_delay,
        max_delay=project_settings.max_delay,
        checkpoint_path=run.checkpoint_excel,
        checkpoint_interval=project_settings.checkpoint_interval,
        max_chars=project_settings.max_desc_chars,
    )
    export_enriched(enriched_jobs, run.enriched_excel)

    # 4. Summarize market
    try:
        market_summary = summarize_market(
            enriched_jobs,
            primary_model=project_settings.primary_summarizer,
            fallback_model=project_settings.fallback_summarizer,
            max_length=project_settings.max_summary_tokens,
            min_length=project_settings.min_summary_tokens,
            max_desc_chars=project_settings.max_desc_chars,
        )
    finally:
        unload_summarizer()

    # 5. Analyze skill gap
    report = analyze_skill_gap(
        cv_text,
        market_summary,
        model_name=project_settings.llm_model,
        use_4bit=project_settings.use_4bit,
        max_new_tokens=project_settings.llm_max_new_tokens,
    )

    # 6. Save report
    run.final_report.parent.mkdir(parents=True, exist_ok=True)
    run.final_report.write_text(report, encoding="utf-8")
    logger.info("Gap analysis run %s completed; report at %s", run.run_id, run.final_report)

    return {
        "run_id": run.run_id,
        "keyword": keyword,
        "target_level": target_level,
        "location": location,
        "jobs_found": len(jobs),
        "jobs_filtered": len(filtered_jobs),
        "market_summary": market_summary,
        "report": report,
        "report_path": str(run.final_report),
        "run_directory": str(run.directory),
    }


def execute_description_fetch(
    *,
    jobs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Fetch descriptions for a list of jobs (independent stage)."""

    run = run_service.create_run("description_fetch", {"job_count": len(jobs)})

    enriched_jobs = fetch_descriptions(
        jobs,
        headless=project_settings.headless,
        network_idle=project_settings.network_idle,
        min_delay=project_settings.min_delay,
        max_delay=project_settings.max_delay,
        checkpoint_path=run.checkpoint_excel,
        checkpoint_interval=project_settings.checkpoint_interval,
        max_chars=project_settings.max_desc_chars,
    )
    export_enriched(enriched_jobs, run.enriched_excel)

    logger.info("Description fetch run %s: %d jobs enriched", run.run_id, len(enriched_jobs))
    return {
        "run_id": run.run_id,
        "job_count": len(jobs),
        "enriched_jobs": enriched_jobs,
        "enriched_excel_path": str(run.enriched_excel),
        "run_directory": str(run.directory),
    }


def execute_market_summary(
    *,
    enriched_jobs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Summarize market from enriched jobs (independent stage)."""

    run = run_service.create_run("market_summary", {"job_count": len(enriched_jobs)})

    try:
        summary = summarize_market(
            enriched_jobs,
            primary_model=project_settings.primary_summarizer,
            fallback_model=project_settings.fallback_summarizer,
            max_length=project_settings.max_summary_tokens,
            min_length=project_settings.min_summary_tokens,
            max_desc_chars=project_settings.max_desc_chars,
        )
    finally:
        unload_summarizer()

    logger.info("Market summary run %s completed", run.run_id)
    return {
        "run_id": run.run_id,
        "job_count": len(enriched_jobs),
        "market_summary": summary,
        "run_directory": str(run.directory),
    }
