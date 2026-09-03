"""Rendering. Item 13: the only module in the project allowed to print.

Item 7: no emoji. Windows terminals running cp1256 raise UnicodeEncodeError
on them, which is a real failure mode for the intended user.
"""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from job_radar.pipeline.runner import RunReport

console = Console()

_STATUS_STYLE = {
    "ok": "green",
    "degraded": "yellow",
    "empty": "red",
    "failed": "red",
}


def render(report: RunReport) -> None:
    _render_health(report)
    _render_jobs(report)


def _render_health(report: RunReport) -> None:
    table = Table(title="Source health", title_justify="left")
    table.add_column("Source")
    table.add_column("Status")
    table.add_column("Jobs", justify="right")
    table.add_column("Cards", justify="right")
    table.add_column("Skipped", justify="right")
    table.add_column("Time", justify="right")
    table.add_column("Method")

    for result in report.results:
        methods = ", ".join(f"{k}={v}" for k, v in result.method_breakdown.items())
        table.add_row(
            result.source,
            f"[{_STATUS_STYLE[result.status]}]{result.status.upper()}[/]",
            str(len(result.jobs)),
            str(result.cards_seen),
            str(result.card_errors),
            f"{result.duration_seconds:.1f}s",
            methods or "-",
        )
    console.print(table)


def _render_jobs(report: RunReport) -> None:
    jobs = report.jobs
    if not jobs:
        console.print(
            "[red]No jobs collected. Check the source health table above "
            "before assuming the market is quiet.[/]"
        )
        return

    table = Table(title=f"{len(jobs)} jobs for '{report.keyword}'", title_justify="left")
    table.add_column("#", justify="right")
    table.add_column("Platform")
    table.add_column("Title")
    table.add_column("Company")
    table.add_column("Location")

    for index, job in enumerate(jobs, 1):
        table.add_row(
            str(index),
            job.platform,
            job.title,
            job.company or "[dim]unknown[/]",
            job.location or "[dim]-[/]",
        )
    console.print(table)

    console.print()
    for index, job in enumerate(jobs, 1):
        console.print(f"{index}. {job.url or '[dim]no link[/]'}")
