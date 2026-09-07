# Merge notes — scraper layer rewrite + stage 2

## What this merge actually is

Carrery is well ahead of the standalone `job-radar` project on scope: five
boards, real concurrency, a SQLite cache, relevance filtering, description
fetching, embeddings and skill-gap analysis. Dropping `job-radar` in as a
second project would have been wrong.

What Carrery had *not* absorbed was the stage 0/1 fixes: `src/scrapers/`
was still the original notebook code, copy-pasted five times. So this merge
ports the fixes into the existing scraper layer rather than adding a parallel
project, and then builds stage 2 on top.

## Three fatal bugs found in the uploaded code

All three were invisible because every scraper wrapped its whole body in
`except Exception: logger.exception(...)`, and `unified.py` did the same
around each future.

**1. `linkedin.py` — `NameError` on every run.** It called `time.sleep(2)`
and `re.sub(...)` while importing neither `time` nor `re`. The sleep was the
first statement after the fetch, so the function raised immediately and
returned `[]`. **LinkedIn contributed zero jobs, always.**

**2. `bayt.py` — no `return` statement.** The function fell off the end and
returned `None`. `unified.py` then called `all_jobs.extend(None)`, raising
`TypeError`, caught and logged as "Bayt scraper failed unexpectedly".
**Bayt contributed zero jobs, always.**

**3. `jobzella.py` — same missing `return`.** **Zero jobs, always.**

Only Wuzzuf and Indeed returned data, and Indeed's `span.companyName` is
retired markup that matches nothing on the current site — so its company
column was `"N/A"` throughout.

Reproduced and verified; `tests/test_scrapers_and_ledger.py` locks all three
out with an AST check that finds attribute bases which are never imported,
and an assertion that no scraper returns `None`.

**The cache made this worse.** `unified.py` cached results unconditionally
(the BUG-011 comment). A run where three boards were dead got cached and was
indistinguishable from a quiet day. `unified.py` now refuses to cache a run
in which every source failed.

## Changed

| File | Change |
|---|---|
| `src/scrapers/config/sources.yaml` | **new** — all selectors and URL templates for the five boards |
| `src/scrapers/extraction.py` | **new** — normalisation, JSON-LD, config-driven CSS |
| `src/scrapers/engine.py` | **new** — generic collector + `CollectionResult` health model |
| `src/scrapers/runner.py` | **new** — wires config, fetcher and relevance filter |
| `src/scrapers/{wuzzuf,linkedin,indeed,bayt,jobzella}.py` | reduced to thin wrappers; signatures unchanged |
| `src/scrapers/common.py` | added `annotate_cross_platform_duplicates` |
| `src/scrapers/unified.py` | health-aware; will not cache a fully failed run |
| `src/job_ledger.py` | **new** — stage 2 |

Fixes ported from stage 0/1: honest health reporting, `None` instead of a
guessed company, per-card error isolation, `quote_plus` encoding, no
character stripping from names, no post-fetch sleep, LinkedIn moved to the
guest endpoint, an explicit job-link selector so the company anchor is never
stored as the job URL, and Scrapling confined to transport with lxml doing
all parsing.

The public contract is unchanged: `scrape_*(keyword, location, headless,
network_idle) -> list[dict]` with `Platform/Title/Company/Link`. `JobListing`
has `extra="allow"`, so the new `is_new`, `first_seen_at`, `fingerprint`,
`duplicate_group` and `also_on` keys flow through the API without a schema
change.

## Stage 2

**Item 14 — `src/job_ledger.py`.** Deliberately *not* the existing
`CacheManager`. The cache answers "what did query X return recently, so I can
skip re-scraping" — it expires, and it is keyed by query. It cannot answer
"which of these have I not seen before". The ledger is keyed by the listing,
never expires, and records `first_seen_at` / `last_seen_at` / `times_seen`.

**Item 15 — duplicates are marked, not collapsed**, as agreed. The same role
on two boards gets a shared `duplicate_group` and an `also_on` list, and both
rows survive with both application links. Matching normalises punctuation,
strips noise words (`remote`, `full time`, `urgent`) and sorts tokens, so
"Senior AI Engineer (Remote)" matches "AI Engineer, Senior — remote".
A job whose company is unknown never groups: two unrelated "AI Engineer"
posts with `Company="N/A"` are not the same job, and grouping them would hide
one.

Matching uses stdlib token normalisation rather than adding `rapidfuzz`.
`requirements.txt` already carries torch, transformers and sentence-transformers;
for title matching the token approach is sufficient and costs nothing.

**Item 16 — `is_new`** is set only the first time a fingerprint is ever seen.
`job_ledger.new_only(jobs)` filters to those.

## Tests

```bash
pytest tests/test_scrapers_and_ledger.py -q --noconftest    # 35 passed in 0.24s
```

`--noconftest` because the existing `tests/conftest.py` imports `fitz`
(PyMuPDF); these tests need no ML dependencies and no browser.

## Not done

Pagination, retry/backoff, rate limiting and proxy rotation (items 17, 19,
20, 23). `search_url_template` already carries `{start}` for pagination.

## Worth checking before you trust the numbers

Every selector in `sources.yaml` was written from the markup the old scrapers
targeted, and Indeed's was already stale. Run each board once with
`--log-level DEBUG` and confirm the health table reads `ok` rather than
`empty` before drawing any conclusions from a run.
