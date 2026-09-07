def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ready(client):
    response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["cache_database"]["status"] == "ok"
    assert body["checks"]["pdf_extraction"]["status"] == "ok"
    assert body["checks"]["scraping_engine"]["status"] == "ok"


def test_cache_stats(client):
    response = client.get("/api/v1/cache/stats")
    assert response.status_code == 200
    body = response.json()
    assert set(body["tables"]) == {
        "job_descriptions", "market_summaries", "skill_embeddings", "job_searches"
    }
