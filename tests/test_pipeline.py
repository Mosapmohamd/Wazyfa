import app.services.analysis_service as analysis_service
import app.services.pipeline_service as pipeline_service
from config import settings as project_settings


def _upload_cv(client, sample_pdf):
    with open(sample_pdf, "rb") as fh:
        response = client.post(
            "/api/v1/cv/extract",
            files={"file": ("cv.pdf", fh, "application/pdf")},
        )
    assert response.status_code == 200
    return response.json()["upload_id"]


def test_pipeline_lifecycle(client, monkeypatch, sample_pdf, tmp_path):
    upload_id = _upload_cv(client, sample_pdf)

    monkeypatch.setattr(
        pipeline_service, "unified_job_scraper",
        lambda **kwargs: [
            {"Platform": "Wuzzuf", "Title": "Junior AI Engineer",
             "Company": "X", "Link": "http://x/1"}
        ],
    )
    monkeypatch.setattr(
        analysis_service, "fetch_descriptions",
        lambda jobs, **kwargs: [
            {**job, "Job_Description": "Requires python and pytorch."} for job in jobs
        ],
    )
    monkeypatch.setattr(analysis_service, "export_enriched", lambda jobs, path: path)
    monkeypatch.setattr(
        analysis_service, "summarize_market",
        lambda jobs, **kwargs: "Market requires Python, PyTorch, Docker.",
    )
    monkeypatch.setattr(analysis_service, "unload_summarizer", lambda: None)
    monkeypatch.setattr(
        analysis_service, "analyze_skill_gap",
        lambda cv_text, market_summary, **kwargs: '{"summary": {"readiness": "Ready"}}',
    )
    monkeypatch.setattr(
        project_settings, "final_report_txt", tmp_path / "report.txt"
    )

    start = client.post(
        "/api/v1/pipeline/run",
        data={
            "keyword": "AI Engineer",
            "target_level": "Junior",
            "cv_upload_id": upload_id,
        },
    )
    assert start.status_code == 202
    job_id = start.json()["id"]

    status = client.get(f"/api/v1/pipeline/jobs/{job_id}")
    assert status.status_code == 200
    body = status.json()
    assert body["status"] == "completed"
    assert body["result"]["jobs_found"] == 1
    assert body["result"]["jobs_filtered"] == 1
    assert body["result"]["market_summary"].startswith("Market requires")
    assert "readiness" in body["result"]["report"]


def test_pipeline_requires_cv(client):
    response = client.post(
        "/api/v1/pipeline/run",
        data={"keyword": "AI Engineer", "target_level": "Junior"},
    )
    assert response.status_code == 400
    assert "cv_file" in response.json()["detail"]


def test_pipeline_invalid_level(client):
    response = client.post(
        "/api/v1/pipeline/run",
        data={"keyword": "AI Engineer", "target_level": "Wizard"},
    )
    assert response.status_code == 400


def test_pipeline_unknown_upload(client):
    response = client.post(
        "/api/v1/pipeline/run",
        data={
            "keyword": "AI Engineer",
            "target_level": "Junior",
            "cv_upload_id": "nope",
        },
    )
    assert response.status_code == 404
