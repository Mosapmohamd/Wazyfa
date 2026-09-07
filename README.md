# AI Job Skill Gap Analyzer

The AI Job Skill Gap Analyzer compares a candidate CV with current job-market requirements. It extracts text from a PDF CV, infers a likely role and seniority, discovers matching jobs from multiple job boards, filters listings by seniority, fetches descriptions, summarizes market requirements, and produces a structured skill-gap report.

This repository is a Python prototype with both a command-line pipeline and a FastAPI service. Scraping and local model inference are resource-intensive and depend on live websites, browser binaries, and the selected runtime hardware. Review the limitations below before deploying it publicly.

## Current capabilities

The project provides two API workflows. In **CV mode**, the client uploads a PDF and may optionally provide a job keyword or target seniority. When those values are omitted, the service extracts text and infers them from the CV. It then runs the full CV-to-market-to-skill-gap pipeline. In **manual mode**, the client supplies a job keyword and target seniority without uploading a CV; the service returns matching jobs and a market summary.

The repository also includes a synchronous CLI, a SQLite cache, checkpoint and manifest files for description enrichment, local Hugging Face summarization and causal-language-model inference, an explicitly opt-in NVIDIA NIM fallback, and an asynchronous FastAPI wrapper.

## Architecture

| Component | Responsibility |
|---|---|
| `config.py` | Environment-backed pipeline settings (pydantic-settings): model names, limits, and data paths. |
| `src/cache_manager.py` | Thread-safe SQLite cache for searches, descriptions, summaries, embeddings, and statistics. |
| `src/cv_extractor.py` | PDF text extraction through PyMuPDF. |
| `src/cv_profile_extractor.py` | Lightweight role, seniority, and skill inference from extracted text. |
| `src/scrapers/` | Job-board scrapers, one module per source (Wuzzuf, LinkedIn, Indeed, Bayt, Jobzella), plus shared relevance/dedup helpers and the unified cached entry point. `src/job_scraper.py` remains as a backward-compatible shim. |
| `src/job_filter.py` | Seniority matching, unknown-level handling, and Excel export. |
| `src/description_fetcher.py` | Description extraction, cache lookup, spawned-worker processing, Excel checkpoints, and checkpoint manifests. |
| `src/market_summarizer.py` | Cached market summarization with NVIDIA opt-in, local primary/fallback models, or truncated-source fallback. |
| `src/skill_gap/` | Skill-gap analysis package: prompt templates, local HF model loader, external-provider paths, and the deterministic fallback. `src/skill_gap_analyzer.py` remains as a backward-compatible shim. |
| `main.py` | CLI entry point delegating to the shared pipeline service (same orchestration and run-scoped artifacts as the API). |
| `app/main.py` | FastAPI application factory. |
| `app/core/config.py` | API-layer settings (CORS, upload limits, job history). |
| `app/core/exceptions.py` | Custom exception classes mapped to HTTP status codes. |
| `app/schemas/` | Request/response validation (Pydantic models). |
| `app/services/` | Business logic: CV extraction, job search, the shared analysis chain, pipeline orchestration, caching. |
| `app/api/routes/` | API endpoint handlers (health, CV, jobs, pipeline, cache). |

The normal request flow is:

```text
Client
  ↓
FastAPI (app/main.py)
  ↓
API routes (app/api/routes/) → Services (app/services/)
  ↓
Existing project modules (src/, config.py)
  ↓
PDF extraction and CV profile inference (CV mode)
  ↓
Job discovery and SQLite search cache
  ↓
Seniority filtering and description enrichment
  ↓
Market summary
  ↓
Skill-gap analysis
  ↓
JSON API response and/or text report
```

## Requirements and installation

Use Python 3.11 or newer. Local model inference may require substantial RAM and, for practical performance, a CUDA-capable GPU. The deterministic analyzer fallback does not require successful local LLM inference, but the complete pipeline still requires the scraping and document-processing dependencies.

Create an isolated environment and install the declared dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Install the Chromium browser used by Scrapling’s dynamic and stealth fetchers:

```bash
python -m playwright install chromium
```

On a Linux server where browser system libraries are not already present, install them with:

```bash
python -m playwright install --with-deps chromium
```

The manifest uses compatible version ranges rather than a lockfile. For production, generate and test a deployment-specific lock or constraints file, then keep it under release control.

**Important:** Run all commands from the project root so that `src` and `config` resolve correctly.

## Configuration

All credentials must be supplied through environment variables or a `.env` file. Do not commit API keys, CVs, reports, logs, databases, or model caches.

### Environment variables

Copy `.env.example` to `.env` and configure as needed:

```bash
cp .env.example .env
# Edit .env with your settings
```

**API Settings** (prefixed with `API_`):
- `API_DEBUG`: Enable debug mode (default: `false`)
- `API_CORS_ORIGINS`: Comma-separated CORS allowlist; empty disables CORS (default: empty)
- `API_UPLOAD_DIR`: Directory for CV uploads (default: `data/uploads`)
- `API_MAX_UPLOAD_SIZE_MB`: Maximum upload size in MB (default: `10`)
- `API_JOB_HISTORY_LIMIT`: Max in-memory job records to retain (default: `200`)

**Pipeline Settings** (from existing `config.py`):
- `SCRAPER_HEADLESS`: Whether browser fetchers run headlessly (default: `true`)
- `SCRAPER_NETWORK_IDLE`: Whether fetchers wait for network idle (default: `true`)
- `LLM_USE_4BIT`: Enables 4-bit quantization on supported CUDA (default: `false`)
- `SKIP_HF_SUMMARIZER`: Skip local summarizer; use truncated fallback (default: `false`)
- `USE_NVIDIA_NIM`: Route skill analysis to NVIDIA NIM fallback (default: `false`)
- `ALLOW_EXTERNAL_AI`: Permit CV/job text to external AI provider (default: `false`)
- `NVIDIA_API_KEY`: Credential for optional NVIDIA-compatible API (unset by default)

When `ALLOW_EXTERNAL_AI=false`, external AI is not called even if `NVIDIA_API_KEY` is present. Enabling external processing should be a deliberate privacy decision.

## Running the CLI

The CLI uses the default CV path `data/resume.pdf`, keyword `AI Engineer`, and target level `Junior`:

```bash
python main.py
```

Custom parameters can be supplied as follows:

```bash
python main.py \
  --keyword "Data Scientist" \
  --cv data/resume.pdf \
  --level "Mid-Level"
```

Supported target levels are `Intern`, `Entry-Level`, `Junior`, `Mid-Level`, `Senior`, `Lead`, `Manager`, and `Director`.

The CLI uses the synchronous pipeline and writes its configured artifacts under `data/`. It requires the scraping dependency and browser runtime even when the local model later falls back to deterministic analysis.

## Running the API

For local development with auto-reload:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

For a production server:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The interactive OpenAPI documentation is available at `http://localhost:8000/docs` and ReDoc at `http://localhost:8000/redoc`.

### Example workflow

**1. Extract CV profile:**
```bash
curl -X POST http://127.0.0.1:8000/api/v1/cv/extract \
  -F "file=@data/resume.pdf"
```
Returns `upload_id` for use in the pipeline.

**2. Run full pipeline:**
```bash
curl -X POST http://127.0.0.1:8000/api/v1/pipeline/run \
  -F "cv_upload_id=<upload_id>" \
  -F "keyword=AI Engineer" \
  -F "target_level=Junior" \
  -F "location=Egypt"
```
Returns `job_id` (202 Accepted).

**3. Poll for results:**
```bash
curl http://127.0.0.1:8000/api/v1/pipeline/jobs/<job_id>
```

**4. Search jobs only:**
```bash
curl -X POST http://127.0.0.1:8000/api/v1/jobs/search \
  -H "Content-Type: application/json" \
  -d '{"keyword": "AI Engineer", "location": "Egypt", "target_level": "Junior"}'
```
Returns `job_id` for polling.

**5. Retrieve cached jobs (24h TTL):**
```bash
curl "http://127.0.0.1:8000/api/v1/jobs/cached?keyword=AI%20Engineer&location=Egypt"
```

### API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness check. |
| `GET` | `/ready` | Readiness check (dependencies). |
| `POST` | `/api/v1/cv/extract` | Upload CV PDF → extract profile (role/level/skills). |
| `POST` | `/api/v1/jobs/search` | Start async job search (returns job_id, 202). |
| `GET` | `/api/v1/jobs/search/{job_id}` | Poll job search status/results. |
| `GET` | `/api/v1/jobs/cached` | Fetch cached job search (24h TTL). |
| `POST` | `/api/v1/pipeline/run` | Start full pipeline (CV → jobs → summary → skill gap). |
| `GET` | `/api/v1/pipeline/jobs/{job_id}` | Poll pipeline status and final report. |
| `GET` | `/api/v1/cache/stats` | Cache database statistics. |

All POST endpoints that run scraping/LLM inference are **asynchronous background jobs**. They return HTTP 202 (Accepted) with a `job_id`, and you poll via GET with that `job_id` to retrieve the result once `status` is `"completed"`.

### Known API limitations

- **In-memory job storage:** Job records and upload registries are lost on process restart. Use one worker process; scale horizontally with a load balancer and persistent storage if needed.
- **Blocking work runs off-event-loop:** Scraping, LLM inference, and description fetching run via `asyncio.to_thread` to avoid blocking the FastAPI event loop.
- **Model loading is lazy and global:** Models load once on first use and remain in memory for the lifetime of the process.

## Generated data and retention

The CLI and the API share one pipeline implementation: `app/services/pipeline_service.execute_pipeline` adds job discovery (scraping) on top of the shared analysis chain in `app/services/analysis_service.execute_analysis` (filter → enrich → summarize → analyze). Every run — CLI or API — writes its artifacts into an isolated run directory, preventing concurrent runs from overwriting shared files.

| Artifact | Purpose |
|---|---|
| `data/runs/<run_id>/Filtered_AI_Jobs.xlsx` | Filtered listings for the run. |
| `data/runs/<run_id>/Jobs_with_Descriptions.xlsx` | Enriched listings for the run. |
| `data/runs/<run_id>/Jobs_Checkpoint.xlsx` and companion JSON | Checkpoint and manifest for description processing. |
| `data/runs/<run_id>/Final_Skill_Gap_Report.txt` | Final report for the run. |
| `data/pipeline_errors.log` | Pipeline log created by the CLI logger. |
| `data/system_cache.db` | SQLite cache for searches, descriptions, summaries, and embeddings. |

CVs and generated reports are sensitive. Define a retention period, restrict filesystem permissions, use HTTPS, and remove data when it is no longer needed. The `.gitignore` protects common generated and secret files from accidental commits, but it is not an access-control mechanism.

## Known limitations and technical debt

The scraper depends on live HTML structures and may require selector updates when source sites change. Job-board availability, anti-bot controls, and browser configuration can cause partial results. The current source adapters log individual scraper failures and aggregate results from the remaining sources.

The API and CLI share process-global pipeline settings, and the analysis chain still runs its blocking stages on threads rather than a request-scoped context. The API’s run-directory isolation must be tested carefully under concurrent requests, and the current implementation should be deployed with one worker until the pipeline context is made fully request-scoped. The in-memory rate limiter is not shared across workers or replicas.

Seniority and CV-profile inference are heuristic. Ambiguous profiles expose inference metadata, but the system should not be treated as an authoritative assessment without user review. Unknown job seniority is represented explicitly where possible, and market quality depends on the source titles and descriptions.

Local model inference can consume substantial RAM/VRAM. `SKIP_HF_SUMMARIZER=true` provides a memory-constrained summarization path, while deterministic keyword analysis remains a lower-quality fallback. External NVIDIA processing is disabled unless `ALLOW_EXTERNAL_AI=true` and a valid key are both configured.

The repository includes a pytest suite covering the API endpoints (health, CV, jobs, pipeline, analysis, stages) and the job filter. It does not yet include a dependency lockfile or CI workflow, and coverage of cache CRUD, PDF edge cases, and model-output parsing is still limited.

## Basic validation

After installing dependencies, compile the Python modules:

```bash
python -m compileall -q config.py main.py app src
```

Run the test suite:

```bash
python -m pytest -q
```

Check repository whitespace:

```bash
git diff --check
```

Start the API and verify liveness:

```bash
curl http://127.0.0.1:8000/health
```

Before production deployment, add tests for cache CRUD, PDF edge cases, concurrent request isolation, model-output parsing, and external-AI opt-in behavior.

## Security checklist

Before public deployment, set an explicit CORS allowlist via `API_CORS_ORIGINS`, run behind HTTPS, restrict filesystem access to the upload/data directories, define CV retention/deletion policies, and verify that external AI is disabled unless approved. Do not log CV contents, API keys, or raw model prompts.

## License and project status

No license file or release process is currently included in the repository. Treat the project as an actively developed prototype until deployment, testing, dependency locking, and privacy controls are completed.
