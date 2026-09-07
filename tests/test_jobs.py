from app.services import cache_service


FAKE_JOBS = [
    {"Platform": "Wuzzuf", "Title": "Junior AI Engineer", "Company": "X", "Link": "http://x/1"},
    {"Platform": "LinkedIn", "Title": "AI Engineer", "Company": "Y", "Link": "http://y/2"},
]


def test_search_job_lifecycle(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.job_service.unified_job_scraper",
        lambda **kwargs: list(FAKE_JOBS),
    )
    start = client.post(
        "/api/v1/jobs/search", json={"keyword": "AI Engineer", "location": "Egypt"}
    )
    assert start.status_code == 202
    job_id = start.json()["id"]

    status = client.get(f"/api/v1/jobs/search/{job_id}")
    assert status.status_code == 200
    body = status.json()
    assert body["status"] == "completed"
    assert body["result"]["total_found"] == 2
    assert len(body["result"]["jobs"]) == 2


def test_search_with_level_filter(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.job_service.unified_job_scraper",
        lambda **kwargs: list(FAKE_JOBS),
    )
    start = client.post(
        "/api/v1/jobs/search",
        json={"keyword": "AI Engineer", "location": "Egypt", "target_level": "Junior"},
    )
    job_id = start.json()["id"]
    body = client.get(f"/api/v1/jobs/search/{job_id}").json()
    # Balanced rule: "Junior AI Engineer" matches explicitly, plain "AI Engineer"
    # has no junior label but is kept as 'unknown' level (conflicts are excluded).
    assert body["result"]["total_after_filter"] == 2


def test_search_invalid_keyword(client):
    response = client.post(
        "/api/v1/jobs/search", json={"keyword": "a", "location": "Egypt"}
    )
    assert response.status_code == 422


def test_search_unknown_job_id(client):
    assert client.get("/api/v1/jobs/search/does-not-exist").status_code == 404


def test_cached_jobs_not_found(client):
    response = client.get(
        "/api/v1/jobs/cached",
        params={"keyword": "Nonexistent Role XYZ", "location": "Nowhere"},
    )
    assert response.status_code == 404


def test_cached_jobs_found(client, monkeypatch):
    class FakeCache:
        def get_cached_search(self, keyword, location, **kwargs):
            return [FAKE_JOBS[0]]

    monkeypatch.setattr(cache_service, "system_cache", FakeCache())
    response = client.get(
        "/api/v1/jobs/cached",
        params={"keyword": "AI Engineer", "location": "Egypt"},
    )
    assert response.status_code == 200
    assert response.json()["count"] == 1
