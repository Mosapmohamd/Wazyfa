"""Application exceptions mapped to HTTP responses centrally."""

from __future__ import annotations


class AppError(Exception):
    """Base error carrying an HTTP status code and a client-safe message."""

    status_code: int = 500

    def __init__(self, detail: str, status_code: int | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        if status_code is not None:
            self.status_code = status_code


class InvalidInputError(AppError):
    status_code = 400


class ResourceNotFoundError(AppError):
    status_code = 404


class CVExtractionError(AppError):
    status_code = 422


class ExternalServiceError(AppError):
    status_code = 502
