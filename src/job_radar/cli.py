"""Typer entry point."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer
from loguru import logger

from job_radar.config.settings import settings
from job_radar.config.sources import load_sources
from job_radar.pipeline import runner
from job_radar.reporting import console as reporting

app = typer.Typer(add_completion=False, help="Job Radar -- multi-source job collector.")


def _configure_logging(level: str) -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level=level.upper(),
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
    )


@app.command()
def search(
    keyword: Annotated[str, typer.Option("--keyword", "-k")] = settings.default_keyword,
    location: Annotated[str, typer.Option("--location", "-l")] = settings.default_location,
    sources_file: Annotated[Path, typer.Option("--sources")] = settings.sources_file,
    log_level: Annotated[str, typer.Option("--log-level")] = settings.log_level,
) -> None:
    """Collect jobs from every enabled source."""
    _configure_logging(log_level)
    sources = load_sources(sources_file)
    report = runner.run(sources, keyword=keyword, location=location)
    reporting.render(report)
    raise typer.Exit(code=report.exit_code)


if __name__ == "__main__":
    app()
