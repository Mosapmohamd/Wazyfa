"""Tests for the new analysis and stage-separation endpoints."""

import app.services.analysis_service as analysis_service
import app.services.cv_analysis_service as cv_analysis_service
import app.services.pipeline_service as pipeline_service
from app.services.runtime import job_store
from config import settings as project_settings


# ── helpers ──

FAKE_JOBS = [
    {"Platform": "Wuzzuf", "Title": "Junior AI Engineer",
     "Company": "X", "Link": "http://x/1"},
    {"Platform": "LinkedIn", "Title": "AI Engineer",
     "Company": "Y", "Link": "http://y/2"},
]

ENRICHED_JOBS = [
    {**job, "Job_Description": "Requires python, pytorch, and docker."}
    for job in FAKE_JOBS
]


def _upload_cv(client, sample_pdf):
    with open(sample_pdf, "rb") as fh:
        response = client.post(
            "/api/v1/cv/extract",
            files={"file": ("cv.pdf", fh, "application/pdf")},
        )
    assert response.status_code == 200
    return response.json()["upload_id"]


def _start_search(client, monkeypatch, keyword="AI Engineer", level=None):
    monkeypatch.setattr(
        "app.services.job_service.unified_job_scraper",
        lambda **kw: list(FAKE_JOBS),
    )
    body = {"keyword": keyword, "location": "Egypt"}
    if level:
        body["target_level"] = level
    response = client.post("/api/v1/jobs/search", json=body)
    assert response.status_code == 202
    return response.json()["id"]


# ── search-from-cv ──

def test_search_from_cv(client, monkeypatch, sample_pdf):
    upload_id = _upload_cv(client, sample_pdf)
    monkeypatch.setattr(
        "app.services.job_service.unified_job_scraper",
        lambda **kw: list(FAKE_JOBS),
    )

    response = client.post(
        "/api/v1/jobs/search-from-cv",
        json={"upload_id": upload_id},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["extracted_role"] == "Machine Learning Engineer"
    assert body["used_keyword"] == "Machine Learning Engineer"
    assert body["used_target_level"] == "Junior"

    # Poll for completion
    status = client.get(f"/api/v1/jobs/search/{body['id']}")
    assert status.json()["status"] == "completed"
    assert status.json()["result"]["total_found"] == 2


def test_search_from_cv_with_overrides(client, monkeypatch, sample_pdf):
    upload_id = _upload_cv(client, sample_pdf)
    monkeypatch.setattr(
        "app.services.job_service.unified_job_scraper",
        lambda **kw: list(FAKE_JOBS),
    )

    response = client.post(
        "/api/v1/jobs/search-from-cv",
        json={
            "upload_id": upload_id,
            "keyword": "Data Scientist",
            "target_level": "Mid-Level",
        },
    )
    assert response.status_code == 202
    body = response.json()
    assert body["used_keyword"] == "Data Scientist"
    assert body["used_target_level"] == "Mid-Level"


def test_search_from_cv_unknown_upload(client):
    response = client.post(
        "/api/v1/jobs/search-from-cv",
        json={"upload_id": "does-not-exist"},
    )
    assert response.status_code == 404


# ── gap analysis ──

def test_analysis_run_lifecycle(client, monkeypatch, sample_pdf, tmp_path):
    upload_id = _upload_cv(client, sample_pdf)
    search_job_id = _start_search(client, monkeypatch)

    # Mock the analysis chain
    monkeypatch.setattr(
        analysis_service, "fetch_descriptions",
        lambda jobs, **kw: list(ENRICHED_JOBS),
    )
    monkeypatch.setattr(analysis_service, "export_enriched", lambda jobs, path: path)
    monkeypatch.setattr(
        analysis_service, "summarize_market",
        lambda jobs, **kw: "Market requires Python, PyTorch, Docker.",
    )
    monkeypatch.setattr(analysis_service, "unload_summarizer", lambda: None)
    monkeypatch.setattr(
        analysis_service, "analyze_skill_gap",
        lambda cv, ms, **kw: '{"summary": {"readiness": "Ready"}}',
    )
    monkeypatch.setattr(
        analysis_service, "filter_jobs",
        lambda jobs, level, role: [j for j in jobs if "Junior" in j["Title"]],
    )

    response = client.post(
        "/api/v1/analysis/run",
        json={
            "cv_upload_id": upload_id,
            "search_job_id": search_job_id,
            "target_level": "Junior",
        },
    )
    assert response.status_code == 202
    job_id = response.json()["id"]

    status = client.get(f"/api/v1/analysis/jobs/{job_id}")
    assert status.status_code == 200
    body = status.json()
    assert body["status"] == "completed"
    assert body["result"]["jobs_found"] == 2
    assert body["result"]["jobs_filtered"] == 1
    assert "readiness" in body["result"]["report"]
    assert body["result"]["run_id"]


def test_analysis_run_requires_completed_search(client, monkeypatch, sample_pdf):
    upload_id = _upload_cv(client, sample_pdf)
    search_job_id = _start_search(client, monkeypatch)

    # Manually mark the search as failed
    job_store.fail(search_job_id, "simulated failure")

    response = client.post(
        "/api/v1/analysis/run",
        json={
            "cv_upload_id": upload_id,
            "search_job_id": search_job_id,
        },
    )
    assert response.status_code == 400
    assert "not completed" in response.json()["detail"]


def test_analysis_run_unknown_search(client, monkeypatch, sample_pdf):
    upload_id = _upload_cv(client, sample_pdf)
    response = client.post(
        "/api/v1/analysis/run",
        json={
            "cv_upload_id": upload_id,
            "search_job_id": "nope",
        },
    )
    assert response.status_code == 404


# ── CV-only direct analysis ──

def test_cv_direct_analysis(client, monkeypatch, sample_pdf):
    upload_id = _upload_cv(client, sample_pdf)

    # Mock LLM review
    monkeypatch.setattr(
        cv_analysis_service, "_local_llm_cv_review",
        lambda cv_text: '{"detected_skills": {"technical": ["python"], "soft": [], "tools": []}, '
                        '"strengths": ["python"], "missing_information": [], '
                        '"recommended_roles": ["ML Engineer"], "estimated_seniority": "Junior", '
                        '"full_review": "Good CV."}',
    )
    monkeypatch.setattr(cv_analysis_service, "_nvidia_cv_review", lambda cv_text: None)

    response = client.post(
        "/api/v1/analysis/cv-direct",
        json={"upload_id": upload_id},
    )
    assert response.status_code == 202
    job_id = response.json()["id"]

    status = client.get(f"/api/v1/analysis/cv-direct/{job_id}")
    assert status.status_code == 200
    body = status.json()
    assert body["status"] == "completed"
    assert body["result"]["role"] == "Machine Learning Engineer"
    assert body["result"]["target_level"] == "Junior"
    assert "python" in body["result"]["skills"]
    assert "detected_skills" in body["result"]["review"]


def test_cv_direct_analysis_deterministic_fallback(client, monkeypatch, sample_pdf):
    upload_id = _upload_cv(client, sample_pdf)

    # Force all LLM paths to fail
    monkeypatch.setattr(cv_analysis_service, "_local_llm_cv_review", lambda cv_text: None)
    monkeypatch.setattr(cv_analysis_service, "_nvidia_cv_review", lambda cv_text: None)

    response = client.post(
        "/api/v1/analysis/cv-direct",
        json={"upload_id": upload_id},
    )
    job_id = response.json()["id"]
    status = client.get(f"/api/v1/analysis/cv-direct/{job_id}")
    body = status.json()
    assert body["status"] == "completed"
    # Deterministic fallback still returns valid JSON
    assert "detected_skills" in body["result"]["review"]
    assert "full_review" in body["result"]["review"]


# ── independent stages ──

def test_description_fetch_lifecycle(client, monkeypatch):
    search_job_id = _start_search(client, monkeypatch)

    monkeypatch.setattr(
        analysis_service, "fetch_descriptions",
        lambda jobs, **kw: list(ENRICHED_JOBS),
    )
    monkeypatch.setattr(analysis_service, "export_enriched", lambda jobs, path: path)

    response = client.post(
        "/api/v1/descriptions/fetch",
        json={"search_job_id": search_job_id},
    )
    assert response.status_code == 202
    job_id = response.json()["id"]

    status = client.get(f"/api/v1/descriptions/fetch/{job_id}")
    assert status.json()["status"] == "completed"
    assert status.json()["result"]["job_count"] == 2


def test_description_fetch_with_inline_jobs(client, monkeypatch):
    monkeypatch.setattr(
        analysis_service, "fetch_descriptions",
        lambda jobs, **kw: list(ENRICHED_JOBS),
    )
    monkeypatch.setattr(analysis_service, "export_enriched", lambda jobs, path: path)

    response = client.post(
        "/api/v1/descriptions/fetch",
        json={"jobs": FAKE_JOBS},
    )
    assert response.status_code == 202


def test_description_fetch_no_jobs(client):
    response = client.post(
        "/api/v1/descriptions/fetch",
        json={},
    )
    assert response.status_code == 400


def test_market_summary_lifecycle(client, monkeypatch):
    monkeypatch.setattr(
        analysis_service, "summarize_market",
        lambda jobs, **kw: "Market requires Python and PyTorch.",
    )
    monkeypatch.setattr(analysis_service, "unload_summarizer", lambda: None)

    response = client.post(
        "/api/v1/market/summarize",
        json={"enriched_jobs": ENRICHED_JOBS},
    )
    assert response.status_code == 202
    job_id = response.json()["id"]

    status = client.get(f"/api/v1/market/summarize/{job_id}")
    assert status.json()["status"] == "completed"
    assert "Python" in status.json()["result"]["market_summary"]


def test_market_summary_no_jobs(client):
    response = client.post(
        "/api/v1/market/summarize",
        json={},
    )
    assert response.status_code == 400


# ── backward-compatible pipeline (still works with run isolation) ──

def test_pipeline_still_works(client, monkeypatch, sample_pdf, tmp_path):
    upload_id = _upload_cv(client, sample_pdf)

    monkeypatch.setattr(
        pipeline_service, "unified_job_scraper",
        lambda **kw: [FAKE_JOBS[0]],
    )
    monkeypatch.setattr(
        analysis_service, "fetch_descriptions",
        lambda jobs, **kw: list(ENRICHED_JOBS),
    )
    monkeypatch.setattr(analysis_service, "export_enriched", lambda jobs, path: path)
    monkeypatch.setattr(
        analysis_service, "summarize_market",
        lambda jobs, **kw: "Market summary.",
    )
    monkeypatch.setattr(analysis_service, "unload_summarizer", lambda: None)
    monkeypatch.setattr(
        analysis_service, "analyze_skill_gap",
        lambda cv, ms, **kw: '{"summary": {"readiness": "Ready"}}',
    )

    response = client.post(
        "/api/v1/pipeline/run",
        data={
            "cv_upload_id": upload_id,
            "keyword": "AI Engineer",
            "target_level": "Junior",
        },
    )
    assert response.status_code == 202
    job_id = response.json()["id"]

    status = client.get(f"/api/v1/pipeline/jobs/{job_id}")
    body = status.json()
    assert body["status"] == "completed"
    assert body["result"]["run_id"]  # run isolation
    assert body["result"]["run_directory"]
