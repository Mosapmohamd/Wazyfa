"""Independent pipeline stages: description fetching and market summarization.

These allow power users to run individual stages without committing to the
full analysis pipeline.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends

from app.api.dependencies import get_job_store
from app.core.exceptions import InvalidInputError, ResourceNotFoundError
from app.schemas.analysis import (
    DescriptionFetchJobResponse,
    DescriptionFetchRequest,
    DescriptionFetchResult,
    MarketSummaryJobResponse,
    MarketSummaryRequest,
    MarketSummaryResult,
)
from app.schemas.common import JobStatus, job_record_to_dict
from app.services.analysis_service import (
    execute_description_fetch,
    execute_market_summary,
)
from app.services.job_store import JobStore
from app.services.runner import run_job

router = APIRouter()


@router.post(
    "/descriptions/fetch",
    status_code=202,
    response_model=DescriptionFetchJobResponse,
    summary="Fetch job descriptions independently (no analysis)",
    description=(
        "Provide jobs directly or reference a completed search job. "
        "Fetches full descriptions from each job link using the existing "
        "isolated-process fetcher with checkpoint recovery."
    ),
)
def start_description_fetch(
    request: DescriptionFetchRequest,
    background_tasks: BackgroundTasks,
    store: JobStore = Depends(get_job_store),
) -> DescriptionFetchJobResponse:
    jobs = request.jobs

    if jobs is None and request.search_job_id:
        record = store.get(request.search_job_id.strip())
        if record is None or record.job_type != "job_search":
            raise ResourceNotFoundError(
                f"Search job {request.search_job_id!r} not found."
            )
        if record.status != JobStatus.COMPLETED:
            raise InvalidInputError(
                f"Search job {request.search_job_id} is not completed."
            )
        jobs = (record.result or {}).get("jobs", [])

    if not jobs:
        raise InvalidInputError(
            "No jobs provided. Supply 'jobs' in the body or a valid 'search_job_id'."
        )

    record = store.create("description_fetch", {"job_count": len(jobs)})
    background_tasks.add_task(
        run_job,
        record.id,
        execute_description_fetch,
        jobs=jobs,
    )
    return DescriptionFetchJobResponse(**job_record_to_dict(record))


@router.get(
    "/descriptions/fetch/{job_id}",
    response_model=DescriptionFetchJobResponse,
    summary="Get the status/result of a description-fetch job",
)
def get_description_fetch(
    job_id: str,
    store: JobStore = Depends(get_job_store),
) -> DescriptionFetchJobResponse:
    record = store.get(job_id)
    if record is None or record.job_type != "description_fetch":
        raise ResourceNotFoundError(f"Description-fetch job {job_id!r} not found")
    return DescriptionFetchJobResponse(
        **job_record_to_dict(record),
        result=record.result if record.status == JobStatus.COMPLETED else None,
    )


@router.post(
    "/market/summarize",
    status_code=202,
    response_model=MarketSummaryJobResponse,
    summary="Summarize market requirements independently (no analysis)",
    description=(
        "Provide enriched jobs (with Job_Description) directly or reference "
        "a completed description-fetch job. Runs the NVIDIA → LED → BART "
        "summarization chain."
    ),
)
def start_market_summary(
    request: MarketSummaryRequest,
    background_tasks: BackgroundTasks,
    store: JobStore = Depends(get_job_store),
) -> MarketSummaryJobResponse:
    enriched_jobs = request.enriched_jobs

    if enriched_jobs is None and request.description_job_id:
        record = store.get(request.description_job_id.strip())
        if record is None or record.job_type != "description_fetch":
            raise ResourceNotFoundError(
                f"Description-fetch job {request.description_job_id!r} not found."
            )
        if record.status != JobStatus.COMPLETED:
            raise InvalidInputError(
                f"Description-fetch job {request.description_job_id} is not completed."
            )
        enriched_jobs = (record.result or {}).get("enriched_jobs", [])

    if not enriched_jobs:
        raise InvalidInputError(
            "No enriched jobs provided. Supply 'enriched_jobs' or a valid 'description_job_id'."
        )

    record = store.create("market_summary", {"job_count": len(enriched_jobs)})
    background_tasks.add_task(
        run_job,
        record.id,
        execute_market_summary,
        enriched_jobs=enriched_jobs,
    )
    return MarketSummaryJobResponse(**job_record_to_dict(record))


@router.get(
    "/market/summarize/{job_id}",
    response_model=MarketSummaryJobResponse,
    summary="Get the status/result of a market-summary job",
)
def get_market_summary(
    job_id: str,
    store: JobStore = Depends(get_job_store),
) -> MarketSummaryJobResponse:
    record = store.get(job_id)
    if record is None or record.job_type != "market_summary":
        raise ResourceNotFoundError(f"Market-summary job {job_id!r} not found")
    return MarketSummaryJobResponse(
        **job_record_to_dict(record),
        result=record.result if record.status == JobStatus.COMPLETED else None,
    )
