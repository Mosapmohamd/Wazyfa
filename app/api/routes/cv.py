"""CV upload, extraction, and profiling endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile

from app.api.dependencies import get_upload_registry
from app.schemas.cv import CVProfileResponse
from app.services import cv_service
from app.services.cv_service import UploadRegistry

router = APIRouter()


@router.post(
    "/cv/extract",
    response_model=CVProfileResponse,
    summary="Upload a CV PDF and extract its inferred profile",
    description=(
        "Extracts text from the PDF, then infers role, seniority level, and "
        "skills using the project's heuristic extractor. The returned "
        "`upload_id` can be reused to start the full pipeline."
    ),
)
async def extract_cv(
    file: UploadFile = File(..., description="CV file in PDF format"),
    registry: UploadRegistry = Depends(get_upload_registry),
) -> CVProfileResponse:
    upload_id, path = await cv_service.save_upload(file)
    profile = cv_service.extract_profile(path)
    registry.add(path)
    return CVProfileResponse(upload_id=upload_id, **profile)
