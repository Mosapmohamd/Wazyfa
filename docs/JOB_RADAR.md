# Job Radar

Multi-source job collector for the Egyptian market. Stage 0 + 1 of the
agreed plan (items 1–13, plus 22 which fell out naturally).

## Install

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
python -m scrapling install     # one-time browser download
```

## Run

```bash
job-radar --keyword "AI Engineer" --location "Egypt"
job-radar -k "Machine Learning" --log-level DEBUG
```

Exit codes are meaningful, so cron can alert on them:

| Code | Meaning |
|------|---------|
| 0 | all sources healthy |
| 1 | at least one source degraded (fewer results than expected, or cards skipped) |
| 2 | at least one source returned nothing or failed outright |

## Layout

```
config/sources.yaml            all selectors + URL templates  (item 11)
src/job_radar/
  domain/models.py             JobPosting, CollectionResult   (item 12)
  config/sources.py            config schema + URL builder    (items 4, 11)
  config/settings.py           env-overridable runtime settings
  fetching/fetcher.py          Scrapling isolated behind a Protocol
  extraction/normalize.py      whitespace + URL helpers       (items 2, 6)
  extraction/jsonld.py         schema.org JobPosting parser   (item 8)
  extraction/css.py            config-driven CSS, no guessing (item 10)
  collectors/html_collector.py one generic collector          (items 3, 11)
  pipeline/runner.py           orchestration + health check   (item 1)
  reporting/console.py         the only module that prints    (items 7, 13)
tests/test_extraction.py       17 regression tests
```

## Architectural decisions

**Scrapling fetches, lxml parses.** Scrapling's element API has moved between
versions (`.attrib` vs `.attrs`), which is what forced the scattered
`hasattr()` checks in the original script. Converting to raw HTML at the
transport boundary contains that variance in one adapter and makes the entire
extraction layer testable without launching a browser — hence 17 tests that
run in 0.2s.

**Two fetcher kinds.** Wuzzuf is a React SPA and needs the stealth browser.
LinkedIn's guest endpoint returns a plain HTML fragment, so it uses the static
fetcher. Paying browser cost for a fragment is waste, and one fewer browser
launch is one less fingerprint.

**Extraction is a chain, not a swap.** JSON-LD first, configured CSS second,
and `extraction_method` is recorded on every job. If JSON-LD coverage silently
drops to zero, the health table shows it before the data goes wrong.

**Honest correction to the review:** JSON-LD is reliably present on job
*detail* pages, and only sometimes on search-result pages. On listings you
will mostly land on the CSS path. JSON-LD becomes the primary path in stage 4,
when we start fetching individual job pages for the description.

## Not done yet (by design)

Stage 2 — SQLite, dedup, "new since last run" (items 14–16)
Stage 3 — pagination, real concurrency, retry/backoff, rate limiting, more
sources (items 17–23). `search_url_template` already carries `{start}`.
Stage 4 — job descriptions, LLM relevance scoring, tracking (items 24–29)

## Note on scraping

Both sites' terms restrict automated access, and LinkedIn enforces this with
IP and account blocks. Stage 3's rate limiting and proxy rotation reduce the
practical risk for personal daily use. If this ever becomes a product, the
calculus changes and you need actual legal advice.
