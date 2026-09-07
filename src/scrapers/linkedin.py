"""LinkedIn job-board scraper (thin wrapper over the shared engine).

The previous implementation called `time.sleep(2)` and `re.sub(...)` without
importing either module. The resulting NameError was swallowed by a broad
`except Exception`, so this scraper returned zero jobs on every run while
logging a generic failure. Both calls are gone: the sleep was a no-op after
the response had already been materialised, and whitespace normalisation now
happens in the extraction layer.
"""

from __future__ import annotations

from src.scrapers.runner import run_source


def scrape_linkedin(keyword: str, location: str, headless: bool, network_idle: bool) -> list[dict[str, str]]:
    return run_source("linkedin", keyword, location, headless, network_idle).jobs
