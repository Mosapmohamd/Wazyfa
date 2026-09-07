#!/usr/bin/env python
"""Check each job board in isolation.

The API response cannot tell you which boards are working -- forty jobs from
two boards looks identical to forty jobs from five. This does.

    python scripts/check_sources.py
    python scripts/check_sources.py --keyword "Machine Learning" --source wuzzuf
    python scripts/check_sources.py --no-headless        # watch the browser
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.job_ledger import JobLedger  # noqa: E402
from src.scrapers import bayt, indeed  # noqa: E402
from src.scrapers.engine import ScraplingFetcher  # noqa: E402
from src.scrapers.runner import get_sources, run_source  # noqa: E402

STATUS_ICON = {
    "ok": "PASS",
    "no_results": "NONE",
    "degraded": "WARN",
    "broken_cards": "FAIL",
    "broken_fields": "FAIL",
    "failed": "FAIL",
}


def run_one(name: str, keyword: str, location: str, headless: bool):
    if name == "indeed":
        return indeed.collect_indeed(keyword, location, headless, True)
    if name == "bayt":
        return bayt.collect_bayt(keyword, location, headless, True)
    return run_source(name, keyword, location, headless, True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keyword", default="AI Engineer")
    parser.add_argument("--location", default="Egypt")
    parser.add_argument("--source", help="check one board only")
    parser.add_argument("--no-headless", action="store_true")
    parser.add_argument("--show", type=int, default=3, help="sample rows per board")
    parser.add_argument(
        "--dump-html",
        metavar="DIR",
        help="save each board's raw HTML here, for fixing stale selectors",
    )
    parser.add_argument(
        "--ledger", action="store_true", help="run results through the job ledger"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")

    names = [args.source] if args.source else list(get_sources())
    results = []
    all_jobs = []

    if args.dump_html:
        dump_dir = Path(args.dump_html)
        dump_dir.mkdir(parents=True, exist_ok=True)
        for name in names:
            source = get_sources()[name]
            url = source.build_url(
                args.keyword,
                args.location,
                **({"country_slug": "egypt"} if name == "bayt" else {}),
            )
            try:
                html = ScraplingFetcher(source.fetcher, not args.no_headless).fetch(url)
                target = dump_dir / f"{name}.html"
                target.write_text(html, encoding="utf-8")
                print(f"saved {target}  ({len(html):,} bytes)")
            except Exception as exc:
                print(f"could not dump {name}: {exc}")
        return 0

    for name in names:
        print(f"\n{'=' * 72}\n{name.upper()}\n{'=' * 72}")
        result = run_one(name, args.keyword, args.location, not args.no_headless)
        results.append((name, result))

        print(
            f"  status={result.status.upper()}  cards={result.cards_seen}  "
            f"titles={result.titles_found}  relevant={len(result.jobs)}  "
            f"skipped={result.card_errors}  {result.duration_seconds:.1f}s"
        )
        print(f"  {result.diagnosis}")

        all_jobs.extend(result.jobs)

        for job in result.jobs[: args.show]:
            print(f"    - {job['Title']}")
            print(f"      company={job['Company']}  via={job.get('extraction_method')}")
            print(f"      {job['Link']}")

        if result.status == "ok" and result.titles_found and not result.jobs:
            print(
                "  note: extraction works; every listing was filtered out as "
                "irrelevant to the keyword."
            )

    print(f"\n{'=' * 72}\nSUMMARY\n{'=' * 72}")
    for name, result in results:
        print(f"  {STATUS_ICON[result.status]:5} {name:10} {len(result.jobs):3} jobs")

    broken = [n for n, r in results if not r.is_healthy and r.status != "degraded"]
    if broken:
        print(f"\n{len(broken)}/{len(results)} boards are not returning data: {', '.join(broken)}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
