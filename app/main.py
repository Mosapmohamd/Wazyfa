"""FastAPI application factory for the AI Job Skill Gap Analyzer."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import analysis, cache, cv, health, jobs, pipeline, stages
from app.core.config import api_settings, get_cors_origins
from app.core.exceptions import AppError
from app.core.logging import configure_logging
from config import settings as project_settings

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    configure_logging(debug=api_settings.debug)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        api_settings.upload_dir.mkdir(parents=True, exist_ok=True)
        project_settings.ensure_dirs()
        logger.info(
            "Starting %s (debug=%s)", api_settings.app_name, api_settings.debug
        )
        # Never log API keys — only the provider name and whether external AI is allowed.
        logger.info(
            "Pipeline config: llm_model=%s llm_provider=%s allow_external_ai=%s",
            project_settings.llm_model,
            project_settings.llm_provider,
            project_settings.allow_external_ai,
        )
        if project_settings.allow_external_ai:
            logger.info("External AI enabled with provider: %s", project_settings.llm_provider)
        else:
            logger.info("External AI disabled. Using local models only.")
        yield
        logger.info("Shutting down %s", api_settings.app_name)

    app = FastAPI(
        title=api_settings.app_name,
        version="1.1.0",
        lifespan=lifespan,
        debug=api_settings.debug,
    )

    cors_origins = get_cors_origins()
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["*"],
        )

    prefix = api_settings.api_v1_prefix

    @app.get("/", tags=["Health"], summary="API entry point")
    def root() -> dict[str, str]:
        return {
            "name": api_settings.app_name,
            "version": "1.1.0",
            "docs": "/docs",
            "health": "/health",
            "api": prefix,
        }

    app.include_router(health.router, tags=["Health"])
    app.include_router(cv.router, prefix=prefix, tags=["CV"])
    app.include_router(jobs.router, prefix=prefix, tags=["Jobs"])
    app.include_router(pipeline.router, prefix=prefix, tags=["Pipeline"])
    app.include_router(analysis.router, prefix=prefix, tags=["Analysis"])
    app.include_router(stages.router, prefix=prefix, tags=["Stages"])
    app.include_router(cache.router, prefix=prefix, tags=["Cache"])

    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code, content={"detail": exc.detail}
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, _: Exception) -> JSONResponse:
        logger.exception(
            "Unhandled error on %s %s", request.method, request.url.path
        )
        return JSONResponse(
            status_code=500, content={"detail": "Internal server error"}
        )

    return app


app = create_app()