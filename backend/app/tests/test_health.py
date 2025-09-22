def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "ok"

def test_metrics(client):
    resp = client.get("/metrics")
    assert resp.status_code == 200
    body = resp.text
    # 至少要包含我們定義的核心指標
    assert "llm_requests_total" in body
    assert "rag_cache_requests_total" in body
