# app/tests/test_perf_mocked.py
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from starlette.testclient import TestClient

from app.main import app
from app.config import settings


def _p95(latencies):
    if not latencies:
        return 0.0
    xs = sorted(latencies)
    # 最近似 p95 的 index
    k = int(0.95 * (len(xs) - 1))
    return xs[k]


@pytest.mark.perf
def test_perf_mocked_throughput_and_latency(monkeypatch):
    """
    模擬高併發負載但完全不打 OpenAI：
    - mock retrieval / rerank / llm
    - 跳過 rate limit
    - 驗證 p95 與 QPS 門檻
    """

    # 1) 關閉 routes 中的速率限制（避免 429 影響量測）
    import app.routes as routes_mod
    monkeypatch.setattr(routes_mod, "_skip_rate_limit", lambda: True, raising=False)

    # 2) 全部 mock 成本高的外部呼叫
    # 2-1) retrieval：回固定 20 筆候選
    def _fake_retrieve_topk(q: str, k: int):
        return [
            {"id": f"c{i}", "title": f"Doc{i}", "text": "dummy text", "source": "unit", "score": 1.0 - i * 0.01}
            for i in range(20)
        ]
    monkeypatch.setattr("app.retrieval.retrieve_topk", _fake_retrieve_topk, raising=False)

    # 2-2) rerank：只取 top_k，補上 reranker_score
    top_k = getattr(settings, "top_k", 5)
    def _fake_rerank(q, cands):
        return [{**c, "reranker_score": c.get("score", 1.0)} for c in cands[:top_k]]
    monkeypatch.setattr("app.routes.rerank", _fake_rerank, raising=False)

    # 2-3) llm：回固定答案與用量
    fake_llm_resp = {
        "text": "（mock）本系統包含 Ingest、Retrieval、Rerank、LLM 回答等元件。",
        "usage": {"input_tokens": 10, "output_tokens": 8, "total_tokens": 18},
        "cost_usd": 0.0,
    }
    monkeypatch.setattr("app.llm.answer_with_context", lambda q, ctx: fake_llm_resp, raising=False)

    client = TestClient(app)

    # 3) 壓測參數（可調）
    TOTAL = 100   # 總請求數
    CONC  = 20    # 併發數
    PAYLOAD = {"query": "系統架構有哪些元件？"}  # 對應 data/raw/architecture.md

    # 4) 預熱（暖 cache）
    for _ in range(5):
        r = client.post("/ask", json=PAYLOAD)
        assert r.status_code == 200

    # 5) 併發送出請求並量測每筆 latency
    latencies = []
    t0 = time.perf_counter()

    def _one_call():
        t = time.perf_counter()
        resp = client.post("/ask", json=PAYLOAD)
        dt = time.perf_counter() - t
        assert resp.status_code == 200
        return dt

    with ThreadPoolExecutor(max_workers=CONC) as ex:
        futs = [ex.submit(_one_call) for _ in range(TOTAL)]
        for f in as_completed(futs):
            latencies.append(f.result())

    wall = time.perf_counter() - t0
    qps = TOTAL / wall
    p95 = _p95(latencies)

    # 6) 斷言門檻（Day02 驗收：p95 ≤ 3s / QPS ≥ 3）
    # 因為這是全 mock 的 in-process 測試，門檻可以更嚴一些（可按 CI 環境調整）
    assert qps >= 10.0, f"QPS too low: {qps:.2f}"
    assert p95 <= 0.5,  f"p95 too high: {p95:.3f}s"

    # 7) 讓 pytest 輸出可讀資訊
    print(f"\n[perf] TOTAL={TOTAL} CONC={CONC} wall={wall:.3f}s QPS={qps:.2f} p95={p95:.3f}s")
