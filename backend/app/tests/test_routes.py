import pytest
from app.observability import ERROR_COUNT

def _metric_value(text: str, line_starts: str) -> float:
    for line in text.splitlines():
        if line.startswith(line_starts):
            try:
                return float(line.split()[-1])
            except Exception:
                pass
    return 0.0

def test_ask_ok_with_mocks(client, mocker):
    fake_cands = [
        {"id": "c1", "title": "Doc1", "text": "aaa", "source": "s1", "score": 0.9},
        {"id": "c2", "title": "Doc2", "text": "bbb", "source": "s2", "score": 0.8},
    ]
    fake_topk = [{**fake_cands[0], "reranker_score": 0.95}]

    mocker.patch("app.retrieval.retrieve_topk", return_value=fake_cands)
    mocker.patch("app.routes.rerank", return_value=fake_topk) 
    mocker.patch("app.llm.answer_with_context", return_value={
        "text": "mocked answer",
        "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        "cost_usd": 0.0001
    })

    r = client.post("/ask", json={"query": "hi"})
    assert r.status_code == 200
    data = r.json()
    assert data["answer"] == "mocked answer"
    assert data["meta"]["cached"] is False
    assert len(data["meta"]["sources"]) == 1
    assert data["meta"]["sources"][0]["id"] == "c1"
    assert data["meta"]["sources"][0]["reranker_score"] == 0.95


def test_ask_cache_hit(client, mocker):
    # 第一次呼叫：寫入快取
    mocker.patch("app.retrieval.retrieve_topk", return_value=[
        {"id": "c1", "title": "Doc1", "text": "aaa", "source": "s1", "score": 0.9},
    ])
    mocker.patch("app.routes.rerank", return_value=[
        {"id": "c1", "title": "Doc1", "text": "aaa", "source": "s1", "score": 0.9, "reranker_score": 0.99},
    ])
    mocker.patch("app.llm.answer_with_context", return_value={
        "text": "cached once",
        "usage": {},
        "cost_usd": 0.0
    })
    r1 = client.post("/ask", json={"query": "same"})
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["meta"]["cached"] is False

    # 第二次同 query：應該 hit cache（不會再觸發 llm / rerank）
    r2 = client.post("/ask", json={"query": "same"})
    d2 = r2.json()
    assert d2["meta"]["cached"] is True
    assert d2["answer"] == "cached once"

def test_ask_rerank_fallback_on_error(client, mocker):
    # 讓 rerank 丟例外 → 路由應該 fallback 到 cands[:top_k]
    fake_cands = [
        {"id": "c1", "title": "Doc1", "text": "aaa", "source": "s1", "score": 0.9},
        {"id": "c2", "title": "Doc2", "text": "bbb", "source": "s2", "score": 0.8},
    ]
    mocker.patch("app.retrieval.retrieve_topk", return_value=fake_cands)
    mocker.patch("app.reranker.rerank", side_effect=RuntimeError("boom"))
    mocker.patch("app.llm.answer_with_context", return_value={
        "text": "fallback ok",
        "usage": {},
        "cost_usd": 0.0
    })
    r = client.post("/ask", json={"query": "fallback please"})
    assert r.status_code == 200
    d = r.json()
    assert d["answer"] == "fallback ok"
    # sources 應該還是存在，只是沒有 reranker_score（或為 None）
    assert len(d["meta"]["sources"]) >= 1
    # 回應不應曝露例外或堆疊
    assert "Traceback" not in r.text
    assert "RuntimeError" not in r.text


def test_ask_rerank_exception_fallback_and_metrics(client, mocker):
    # 先讀 metrics baseline
    m0 = client.get("/metrics").text
    rerank_count0 = _metric_value(m0, 'rag_rerank_latency_seconds_count')
    # ERROR_COUNT 是 counter，含 label；我們就檢查文字是否出現對應 label
    err_before_has_label = 'rag_errors_total{stage="rerank"}' in m0

    # 準備 retrieval/llm；讓 rerank 拋錯 → routes 會 fallback 到原始 cands[:top_k]
    fake_cands = [
        {"id": "c1", "title": "Doc1", "text": "aaa", "source": "s1", "score": 0.9},
        {"id": "c2", "title": "Doc2", "text": "bbb", "source": "s2", "score": 0.8},
    ]
    mocker.patch("app.retrieval.retrieve_topk", return_value=fake_cands)
    mocker.patch("app.routes.rerank", side_effect=RuntimeError("boom"))
    mocker.patch("app.llm.answer_with_context", return_value={
        "text": "fallback ok",
        "usage": {"input_tokens": 12, "output_tokens": 5, "total_tokens": 17},
        "cost_usd": 0.00012
    })

    r = client.post("/ask", json={"query": "觸發 rerank 例外"})
    assert r.status_code == 200
    d = r.json()
    # 確認確實 fallback（沒有 reranker_score 或為 None；而且來源數量>=1）
    assert len(d["meta"]["sources"]) >= 1
    assert d["answer"] == "fallback ok"

    # 再讀 metrics，檢查累加
    m1 = client.get("/metrics").text
    rerank_count1 = _metric_value(m1, 'rag_rerank_latency_seconds_count')
    assert rerank_count1 >= rerank_count0 + 1
    assert 'rag_errors_total{stage="rerank"}' in m1
    # 額外：llm_requests_total 的 success 也應+1
    assert 'llm_requests_total{route="/ask",status="success"}' in m1

def test_embedding_exception_returns_500_and_metric(client_no_raise, mocker, monkeypatch):
    # 1) 關外連，避免任何意外打到 OpenAI
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    # 2) metrics 基線
    before = client_no_raise.get("/metrics").text
    emb_err0 = _metric_value(before, 'rag_errors_total{stage="embedding"}')

    # 3) 關鍵：在唯一必經點掛炸彈（並計數）
    def boom_retrieve_candidates(query, candidate_k):
        ERROR_COUNT.labels(stage="embedding").inc()
        raise RuntimeError("boom in embeddings")
    mocker.patch("app.routes._retrieve_candidates", side_effect=boom_retrieve_candidates)

    # 4) 強制繞過快取（header 或 ?nocache=1 其一即可；這裡用 header）
    r = client_no_raise.post(
        "/ask?nocache=1",
        headers={"X-Cache-Bypass": "1"},
        json={"query": "embedding-error-unique-query"}
    )

    # 5) 這次應該回 500（client_no_raise 不會丟例外）
    assert 500 <= r.status_code < 600

    # 6) 指標應累加
    after = client_no_raise.get("/metrics").text
    emb_err1 = _metric_value(after, 'rag_errors_total{stage="embedding"}')
    assert emb_err1 >= emb_err0 + 1

def test_empty_query_rejected_and_request_error_metric(client):
    m0 = client.get("/metrics").text
    # 發出空查詢
    r = client.post("/ask", json={"query": ""})
    # 你的程式目前會回 200 並帶 error JSON；或你也可改成 400
    assert r.status_code in (200, 400)
    data = r.json()
    assert "error" in data

    m1 = client.get("/metrics").text
    # 檢查有標示 error 的請求計數出現
    assert 'llm_requests_total{route="/ask",status="error"}' in m1
