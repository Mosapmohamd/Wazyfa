"""Independent analysis endpoints: gap analysis + CV-only review."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends

from app.api.dependencies import get_job_store, get_upload_registry
from app.core.exceptions import InvalidInputError, ResourceNotFoundError
from app.schemas.analysis import (
    AnalysisJobResponse,
    AnalysisRunRequest,
    AnalysisResult,
    CVDirectAnalysisRequest,
    CVDirectAnalysisResult,
    CVDirectJobResponse,
)
from app.schemas.common import JobStatus, job_record_to_dict
from app.services import cv_analysis_service
from app.services.analysis_service import execute_analysis
from app.services.cv_service import UploadRegistry
from app.services.job_store import JobStore
from app.services.runner import run_job

router = APIRouter()


# ────────────────────── Gap analysis (market-based) ──────────────────────

@router.post(
    "/analysis/run",
    status_code=202,
    response_model=AnalysisJobResponse,
    summary="Start gap analysis using a CV and a previously completed job search",
    description=(
        "Requires a cv_upload_id (from POST /cv/extract) and a search_job_id "
        "(from a completed POST /jobs/search). The backend will filter jobs, "
        "fetch descriptions, summarize market requirements, and run the "
        "skill-gap analysis — all in the background."
    ),
)
def start_analysis(
    request: AnalysisRunRequest,
    background_tasks: BackgroundTasks,
    store: JobStore = Depends(get_job_store),
    registry: UploadRegistry = Depends(get_upload_registry),
) -> AnalysisJobResponse:
    # Validate CV upload
    cv_path = registry.get(request.cv_upload_id.strip())
    if cv_path is None or not cv_path.exists():
        raise ResourceNotFoundError(
            f"CV upload {request.cv_upload_id!r} not found. Upload a CV first via POST /cv/extract."
        )

    # Validate search job is completed
    search_record = store.get(request.search_job_id.strip())
    if search_record is None or search_record.job_type != "job_search":
        raise ResourceNotFoundError(
            f"Search job {request.search_job_id!r} not found."
        )
    if search_record.status != JobStatus.COMPLETED:
        raise InvalidInputError(
            f"Search job {request.search_job_id} is not completed "
            f"(status: {search_record.status.value}). Poll GET /jobs/search/{request.search_job_id} first."
        )

    jobs = (search_record.result or {}).get("jobs", [])
    if not jobs:
        raise InvalidInputError("The referenced search job has no jobs in its result.")

    keyword = request.keyword or (search_record.result or {}).get("keyword", "AI Engineer")
    location = request.location or (search_record.result or {}).get("location")

    record = store.create(
        "gap_analysis",
        {
            "cv_upload_id": request.cv_upload_id,
            "search_job_id": request.search_job_id,
            "keyword": keyword,
            "target_level": request.target_level,
            "target_role": request.target_role,
            "location": location,
        },
    )
    background_tasks.add_task(
        run_job,
        record.id,
        execute_analysis,
        cv_path=cv_path,
        jobs=jobs,
        keyword=keyword,
        target_level=request.target_level,
        target_role=request.target_role,
        location=location,
    )
    return AnalysisJobResponse(**job_record_to_dict(record))


@router.get(
    "/analysis/jobs/{job_id}",
    response_model=AnalysisJobResponse,
    summary="Get the status/result of a gap-analysis run",
)
def get_analysis(
    job_id: str,
    store: JobStore = Depends(get_job_store),
) -> AnalysisJobResponse:
    record = store.get(job_id)
    if record is None or record.job_type != "gap_analysis":
        raise ResourceNotFoundError(f"Analysis job {job_id!r} not found")
    return AnalysisJobResponse(
        **job_record_to_dict(record),
        result=record.result if record.status == JobStatus.COMPLETED else None,
    )


# ────────────────────── CV-only direct analysis ──────────────────────

@router.post(
    "/analysis/cv-direct",
    status_code=202,
    response_model=CVDirectJobResponse,
    summary="Start a CV-only review (no market data needed)",
    description=(
        "Analyzes the CV for detected skills, strengths, missing information, "
        "recommended roles, and estimated seniority. Does not search for jobs "
        "or compare against market data."
    ),
)
def start_cv_direct(
    request: CVDirectAnalysisRequest,
    background_tasks: BackgroundTasks,
    store: JobStore = Depends(get_job_store),
    registry: UploadRegistry = Depends(get_upload_registry),
) -> CVDirectJobResponse:
    cv_path = registry.get(request.upload_id.strip())
    if cv_path is None or not cv_path.exists():
        raise ResourceNotFoundError(
            f"CV upload {request.upload_id!r} not found. Upload a CV first via POST /cv/extract."
        )

    record = store.create(
        "cv_direct_analysis",
        {"upload_id": request.upload_id},
    )
    background_tasks.add_task(
        run_job,
        record.id,
        cv_analysis_service.execute_cv_direct_analysis,
        cv_path=cv_path,
        upload_id=request.upload_id,
    )
    return CVDirectJobResponse(**job_record_to_dict(record))


@router.get(
    "/analysis/cv-direct/{job_id}",
    response_model=CVDirectJobResponse,
    summary="Get the status/result of a CV-only review",
)
def get_cv_direct(
    job_id: str,
    store: JobStore = Depends(get_job_store),
) -> CVDirectJobResponse:
    record = store.get(job_id)
    if record is None or record.job_type != "cv_direct_analysis":
        raise ResourceNotFoundError(f"CV-direct analysis job {job_id!r} not found")
    return CVDirectJobResponse(
        **job_record_to_dict(record),
        result=record.result if record.status == JobStatus.COMPLETED else None,
    )
