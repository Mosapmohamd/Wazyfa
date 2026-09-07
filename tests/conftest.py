from __future__ import annotations

import fitz
import pytest
from fastapi.testclient import TestClient

from app.core.config import api_settings
from app.main import create_app
from app.services.runtime import job_store
from app.services import run_service


@pytest.fixture(autouse=True)
def _isolate_runs(tmp_path, monkeypatch):
    """Redirect run_service to use a temporary directory for tests."""
    monkeypatch.setattr(run_service.run_service, "_base_dir", tmp_path / "runs")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(api_settings, "upload_dir", tmp_path / "uploads")
    job_store.clear()
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
    job_store.clear()


@pytest.fixture()
def sample_pdf(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        "Machine Learning Engineer\npython pytorch docker junior",
    )
    path = tmp_path / "cv.pdf"
    doc.save(str(path))
    doc.close()
    return path
