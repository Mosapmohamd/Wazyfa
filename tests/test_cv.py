def test_extract_cv_success(client, sample_pdf):
    with open(sample_pdf, "rb") as fh:
        response = client.post(
            "/api/v1/cv/extract",
            files={"file": ("cv.pdf", fh, "application/pdf")},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "Machine Learning Engineer"
    assert body["target_level"] == "Junior"
    assert "python" in body["skills"]
    assert body["extracted_chars"] > 0
    assert body["upload_id"]


def test_extract_cv_rejects_non_pdf(client):
    response = client.post(
        "/api/v1/cv/extract",
        files={"file": ("cv.txt", b"plain text", "text/plain")},
    )
    assert response.status_code == 400
    assert "PDF" in response.json()["detail"]
