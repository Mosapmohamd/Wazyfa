#!/usr/bin/env python
"""Replay saved HTML dumps through the extraction engine -- no network.

Fixing a stale selector normally means a 10-second browser fetch per attempt,
and boards rate-limit. Dump once, then iterate offline:

    python scripts/check_sources.py --dump-html dumps/
    python scripts/replay_dumps.py dumps/        # edit sources.yaml, re-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.scrapers.common import _is_relevant_job  # noqa: E402
from src.scrapers.engine import collect  # noqa: E402
from src.scrapers.runner import get_sources  # noqa: E402


class DumpFetcher:
    def __init__(self, path: Path) -> None:
        self.path = path

    def fetch(self, url: str) -> str:
        return self.path.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--keyword", default="AI Engineer")
    parser.add_argument("--location", default="Egypt")
    parser.add_argument("--show", type=int, default=5)
    args = parser.parse_args()

    sources = get_sources()
    print(f"{'source':10} {'status':14} {'cards':>6} {'titles':>7} {'relevant':>9}")
    print("-" * 60)

    broken = 0
    for name, source in sources.items():
        path = args.directory / f"{name}.html"
        if not path.exists():
            print(f"{name:10} (no dump)")
            continue

        # The URL is irrelevant when replaying, but the template still needs
        # its placeholders filled.
        if "{country_slug}" in source.search_url_template:
            source = source.model_copy(
                update={"search_url_template": "https://x/{keyword}{location}{start}"}
            )

        result = collect(
            source, args.keyword, args.location, DumpFetcher(path),
            relevance_filter=_is_relevant_job,
        )
        print(
            f"{name:10} {result.status:14} {result.cards_seen:6} "
            f"{result.titles_found:7} {len(result.jobs):9}"
        )
        if not result.is_healthy:
            broken += 1
            print(f"           {result.diagnosis}")
        for job in result.jobs[: args.show]:
            print(f"           - {job['Title'][:52]:52} | {job['Company']}")

    return 2 if broken else 0


if __name__ == "__main__":
    raise SystemExit(main())
