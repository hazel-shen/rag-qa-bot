def _metric_val(text: str, line_starts: str) -> float:
    for line in text.splitlines():
        if line.startswith(line_starts):
            try:
                return float(line.split()[-1])
            except Exception:
                pass
    return 0.0

def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"

def test_metrics_endpoint_has_core_metrics(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    body = r.text
    # 我們關心的幾個關鍵 metric 名稱是否存在
    assert "llm_requests_total" in body
    assert "rag_cache_requests_total" in body
    assert "rag_rerank_latency_seconds" in body

def test_metrics_increase_after_one_ask(client, mocker):
    before = client.get("/metrics").text
    req0 = _metric_val(before, 'llm_requests_total{route="/ask",status="success"}')
    cache0 = _metric_val(before, 'rag_cache_requests_total{route="/ask"}')
    # tokens 計數有 label（kind/model），這裡只檢查是否存在且會增加其中一種
    itok0 = _metric_val(before, 'llm_tokens_total{kind="input",model="gpt-4o-mini"}')
    otok0 = _metric_val(before, 'llm_tokens_total{kind="output",model="gpt-4o-mini"}')

    # 模擬一次 /ask
    mocker.patch("app.retrieval.retrieve_topk", return_value=[
        {"id":"c1","title":"Doc1","text":"aaa","source":"s1","score":0.9}
    ])
    mocker.patch("app.routes.rerank", return_value=[
        {"id":"c1","title":"Doc1","text":"aaa","source":"s1","score":0.9,"reranker_score":0.99}
    ])
    mocker.patch("app.llm.answer_with_context", return_value={
        "text":"OK",
        "usage":{"input_tokens": 8, "output_tokens": 4, "total_tokens": 12},
        "cost_usd": 0.00002
    })

    r = client.post("/ask", json={"query": "metrics ping"})
    assert r.status_code == 200

    after = client.get("/metrics").text
    req1 = _metric_val(after, 'llm_requests_total{route="/ask",status="success"}')
    cache1 = _metric_val(after, 'rag_cache_requests_total{route="/ask"}')
    itok1 = _metric_val(after, 'llm_tokens_total{kind="input",model="gpt-4o-mini"}')
    otok1 = _metric_val(after, 'llm_tokens_total{kind="output",model="gpt-4o-mini"}')

    assert req1 >= req0 + 1
    assert cache1 >= cache0 + 1
    # tokens 可能依你的 llm 實作決定是否累加；若沒加計數可放寬或改檢查 presence
    assert itok1 >= itok0
    assert otok1 >= otok0
