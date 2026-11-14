"""Full CV-to-skill-gap pipeline endpoints (async background job)."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile

from app.api.dependencies import get_job_store, get_upload_registry
from config import settings as project_settings
from src.job_filter import SUPPORTED_LEVELS
from app.core.exceptions import InvalidInputError, ResourceNotFoundError
from app.schemas.common import job_record_to_dict
from app.schemas.pipeline import PipelineJobResponse
from app.services import cv_service, pipeline_service
from app.services.cv_service import UploadRegistry
from app.services.job_store import JobStore
from app.services.runner import run_job

router = APIRouter()


@router.post(
    "/pipeline/run",
    status_code=202,
    response_model=PipelineJobResponse,
    summary="Start the full analysis pipeline (scrape → filter → enrich → summarize → gap analysis)",
    description=(
        "Provide either a previously obtained `cv_upload_id` (from POST /cv/extract) "
        "or a fresh `cv_file` PDF. The pipeline runs in the background; poll "
        "GET /pipeline/jobs/{job_id} for status and the final report."
    ),
)
async def run_pipeline(
    background_tasks: BackgroundTasks,
    store: JobStore = Depends(get_job_store),
    registry: UploadRegistry = Depends(get_upload_registry),
    keyword: str = Form(default_factory=lambda: project_settings.keyword),
    target_level: str = Form(default_factory=lambda: project_settings.target_level),
    target_role: str = Form(default_factory=lambda: project_settings.target_role),
    location: str | None = Form(default=None),
    cv_upload_id: str | None = Form(default=None),
    cv_file: UploadFile | None = File(default=None),
) -> PipelineJobResponse:
    keyword = keyword.strip()
    if len(keyword) < 2:
        raise InvalidInputError("keyword must contain at least 2 characters")
    if target_level not in SUPPORTED_LEVELS:
        raise InvalidInputError(
            f"target_level must be one of: {', '.join(SUPPORTED_LEVELS)}"
        )
    target_role = target_role.strip()
    if not target_role:
        raise InvalidInputError("target_role must not be empty")

    cv_path = None
    if cv_file is not None:
        _, cv_path = await cv_service.save_upload(cv_file)
        registry.add(cv_path)
    elif cv_upload_id:
        cv_path = registry.get(cv_upload_id.strip())
        if cv_path is None or not cv_path.exists():
            raise ResourceNotFoundError(f"CV upload {cv_upload_id!r} not found")
    else:
        raise InvalidInputError(
            "Provide either cv_file (PDF upload) or cv_upload_id."
        )

    record = store.create(
        "pipeline",
        {
            "keyword": keyword,
            "target_level": target_level,
            "target_role": target_role,
            "location": location or project_settings.location,
        },
    )
    background_tasks.add_task(
        run_job,
        record.id,
        pipeline_service.execute_pipeline,
        cv_path=cv_path,
        keyword=keyword,
        target_level=target_level,
        target_role=target_role,
        location=location,
    )
    return PipelineJobResponse(**job_record_to_dict(record))


@router.get(
    "/pipeline/jobs/{job_id}",
    response_model=PipelineJobResponse,
    summary="Get the status/result of a pipeline run",
)
def get_pipeline_job(
    job_id: str,
    store: JobStore = Depends(get_job_store),
) -> PipelineJobResponse:
    record = store.get(job_id)
    if record is None or record.job_type != "pipeline":
        raise ResourceNotFoundError(f"Pipeline job {job_id!r} not found")
    return PipelineJobResponse(
        **job_record_to_dict(record),
        result=record.result if record.status.value == "completed" else None,
    )
