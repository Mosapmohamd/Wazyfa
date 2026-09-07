"""CV upload handling, extraction, and profiling. Wraps existing src logic."""

from __future__ import annotations

import logging
import threading
import uuid
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from app.core.config import api_settings
from app.core.exceptions import CVExtractionError, InvalidInputError
from src.cv_extractor import extract_cv_text
from src.cv_profile_extractor import extract_cv_profile

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 1024 * 1024
_ALLOWED_SUFFIX = ".pdf"


class UploadRegistry:
    """Maps opaque upload ids to stored file paths (in-memory)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: dict[str, Path] = {}

    def add(self, path: Path) -> str:
        upload_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._items[upload_id] = path
        return upload_id

    def get(self, upload_id: str) -> Path | None:
        with self._lock:
            return self._items.get(upload_id)


upload_registry = UploadRegistry()


async def save_upload(file: UploadFile) -> tuple[str, Path]:
    """Validate and persist an uploaded CV PDF. Returns (upload_id, path)."""

    filename = file.filename or "cv.pdf"
    if Path(filename).suffix.lower() != _ALLOWED_SUFFIX:
        raise InvalidInputError("Only PDF files are accepted")

    api_settings.upload_dir.mkdir(parents=True, exist_ok=True)
    max_bytes = api_settings.max_upload_size_mb * 1024 * 1024

    content = bytearray()
    while chunk := await file.read(_CHUNK_SIZE):
        content.extend(chunk)
        if len(content) > max_bytes:
            raise InvalidInputError(
                f"File exceeds the maximum size of {api_settings.max_upload_size_mb} MB"
            )

    if not content:
        raise InvalidInputError("Uploaded file is empty")

    destination = api_settings.upload_dir / f"{uuid.uuid4().hex}_cv.pdf"
    destination.write_bytes(bytes(content))
    logger.info("Stored CV upload %s (%d bytes)", destination.name, len(content))
    return upload_registry.add(destination), destination


def extract_profile(cv_path: Path) -> dict[str, Any]:
    """Extract CV text and infer role/level/skills using existing heuristics."""

    cv_text = extract_cv_text(cv_path)
    if not cv_text:
        raise CVExtractionError(
            "Could not extract text from the CV. It may be image-only or corrupted."
        )
    profile = extract_cv_profile(cv_text)
    profile["extracted_chars"] = len(cv_text)
    return profile
