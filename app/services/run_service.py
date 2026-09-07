"""Run isolation: each analysis/pipeline run gets its own directory.

Prevents concurrent requests from overwriting shared files like
Jobs_with_Descriptions.xlsx, checkpoint files, and reports.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import settings as project_settings

logger = logging.getLogger(__name__)


@dataclass
class RunInfo:
    """Metadata and file paths for a single isolated run."""

    run_id: str
    run_type: str
    created_at: datetime
    params: dict[str, Any] = field(default_factory=dict)
    directory: Path = field(default_factory=Path)
    filtered_excel: Path = field(default_factory=Path)
    enriched_excel: Path = field(default_factory=Path)
    checkpoint_excel: Path = field(default_factory=Path)
    final_report: Path = field(default_factory=Path)


class RunService:
    """Creates isolated directories under data/runs/{run_id}/ for each run."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir or project_settings.data_dir / "runs"

    def create_run(
        self,
        run_type: str,
        params: dict[str, Any] | None = None,
    ) -> RunInfo:
        run_id = uuid.uuid4().hex[:12]
        run_dir = self._base_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        info = RunInfo(
            run_id=run_id,
            run_type=run_type,
            created_at=datetime.now(timezone.utc),
            params=params or {},
            directory=run_dir,
            filtered_excel=run_dir / "Filtered_AI_Jobs.xlsx",
            enriched_excel=run_dir / "Jobs_with_Descriptions.xlsx",
            checkpoint_excel=run_dir / "Jobs_Checkpoint.xlsx",
            final_report=run_dir / "Final_Skill_Gap_Report.txt",
        )
        logger.info("Created run %s (type=%s) at %s", run_id, run_type, run_dir)
        return info


run_service = RunService()
