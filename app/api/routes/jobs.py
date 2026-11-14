"""Job search endpoints (async background jobs + cached lookup)."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from torch.profiler import profile

from app.api.dependencies import get_job_store, get_upload_registry
from app.core.exceptions import InvalidInputError, ResourceNotFoundError
from app.schemas.common import job_record_to_dict
from app.schemas.jobs import (
    CachedJobsResponse,
    JobSearchRequest,
    SearchFromCVRequest,
    SearchFromCVResponse,
    SearchJobResponse,
)
from app.services import cache_service, job_service, cv_service
from app.services.cv_service import UploadRegistry
from app.services.job_store import JobStore
from app.services.runner import run_job

router = APIRouter()


@router.post(
    "/jobs/search",
    status_code=202,
    response_model=SearchJobResponse,
    summary="Start an async multi-platform job search",
    description=(
        "Scrapes Wuzzuf, LinkedIn, Indeed, Bayt, and Jobzella. This takes "
        "several minutes; poll the returned job id via GET /jobs/search/{{job_id}}."
    ),
)
def start_job_search(
    request: JobSearchRequest,
    background_tasks: BackgroundTasks,
    store: JobStore = Depends(get_job_store),
) -> SearchJobResponse:
    record = store.create("job_search", request.model_dump())
    background_tasks.add_task(
        run_job,
        record.id,
        job_service.execute_search,
        keyword=request.keyword,
        location=request.location,
        target_level=request.target_level,
        target_role=request.target_role,
    )
    return SearchJobResponse(**job_record_to_dict(record))


@router.get(
    "/jobs/search/{job_id}",
    response_model=SearchJobResponse,
    summary="Get the status/result of a job search",
)
def get_job_search(
    job_id: str,
    store: JobStore = Depends(get_job_store),
) -> SearchJobResponse:
    record = store.get(job_id)
    if record is None or record.job_type != "job_search":
        raise ResourceNotFoundError(f"Job search {job_id!r} not found")
    return SearchJobResponse(
        **job_record_to_dict(record),
        result=record.result if record.status.value == "completed" else None,
    )


@router.get(
    "/jobs/cached",
    response_model=CachedJobsResponse,
    summary="Return a cached search (24h TTL) if one exists",
)
def get_cached_jobs(
    keyword: str = Query(..., min_length=2, max_length=120),
    location: str = Query(..., min_length=2, max_length=120),
) -> CachedJobsResponse:
    keyword = keyword.strip()
    location = location.strip()
    if not keyword or not location:
        raise InvalidInputError("keyword and location must not be empty")
    jobs = cache_service.get_cached_search(keyword, location)
    if jobs is None:
        raise ResourceNotFoundError(
            f"No cached search for {keyword!r} in {location!r}. "
            "Start a search with POST /jobs/search first."
        )
    return CachedJobsResponse(
        keyword=keyword, location=location, count=len(jobs), jobs=jobs
    )


# ────────────────── CV-driven search ──────────────────

@router.post(
    "/jobs/search-from-cv",
    status_code=202,
    response_model=SearchFromCVResponse,
    summary="Start a search using the CV's extracted role and seniority",
    description=(
        "Extracts the candidate's role and target level from a previously uploaded CV, "
        "then starts a job search using those parameters. Allows optional overrides "
        "for keyword, target_level, and location."
    ),
)
def start_search_from_cv(
    request: SearchFromCVRequest,
    background_tasks: BackgroundTasks,
    store: JobStore = Depends(get_job_store),
    registry: UploadRegistry = Depends(get_upload_registry),
) -> SearchFromCVResponse:
    # Validate CV upload exists
    cv_path = registry.get(request.upload_id.strip())
    if cv_path is None or not cv_path.exists():
        raise ResourceNotFoundError(
            f"CV upload {request.upload_id!r} not found. Upload a CV first via POST /cv/extract."
        )

    # Extract CV profile
    profile = cv_service.extract_profile(cv_path)
    extracted_role = profile.get("role", "AI Engineer")
    extracted_level = profile.get("target_level", "Junior")

    # Determine final search parameters
    final_keyword = request.keyword or extracted_role
    final_level = request.target_level or extracted_level
    final_location = request.location or "Egypt"

    # Start the search
    record = store.create("job_search", {
        "keyword": final_keyword,
        "location": final_location,
        "target_level": final_level,
        "target_role": request.target_role,
        "cv_upload_id": request.upload_id,
    })

    background_tasks.add_task(
        run_job,
        record.id,
        job_service.execute_search,
        keyword=final_keyword,
        location=final_location,
        target_level=final_level,
        target_role=request.target_role,
    )

    return SearchFromCVResponse(
        **job_record_to_dict(record),
        extracted_role=extracted_role,
        extracted_level=extracted_level,
        used_keyword=final_keyword,
        used_target_level=final_level,
        used_location=final_location,
    )
