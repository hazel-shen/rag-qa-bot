# app/tests/test_rate_limit.py
import pytest
from starlette.testclient import TestClient

import app.config as config
from app.main import app
from app.rate_limit import rate_limiter


# --- 測試客戶端 ---
@pytest.fixture()
def client():
    return TestClient(app)


# --- 全域打樁：避免測試打到 OpenAI / 雲端 reranker ---
@pytest.fixture(autouse=True)
def _stub_external_calls(monkeypatch):
    # stub LLM
    def fake_answer_with_context(query, context):
        return {
            "text": f"[stubbed answer] {query}",
            "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            "cost_usd": 0.0,
        }
    monkeypatch.setattr("app.llm.answer_with_context", fake_answer_with_context, raising=True)

    # 若你的 reranker 也會調雲端，可一併打樁
    try:
        def fake_rerank(query, cands):
            # 模擬「原順序即結果」，並附個假分數
            for i, c in enumerate(cands):
                c["reranker_score"] = 1.0 - i * 0.01
            return cands[:]
        monkeypatch.setattr("app.reranker.rerank", fake_rerank, raising=True)
    except Exception:
        pass


# --- 需要「真的測限流」時才啟用的 fixture ---
@pytest.fixture
def enable_real_rate_limit():
    """
    讓 /ask 在測試時不再被 _skip_rate_limit() 跳過，
    並把配額設得很小以便觸發 429。
    """
    old_env = getattr(config.settings, "env", "")
    old_disable = getattr(config.settings, "disable_rate_limit", False)

    # 讓 routes._skip_rate_limit() 不會跳過
    config.settings.env = "dev"              # 任何不是 "test" 的值
    config.settings.disable_rate_limit = False

    # 小額度 + 清桶，保證測試獨立
    rate_limiter.configure(per_ip_per_min=1, per_user_per_min=1, burst=1, disabled=False)
    rate_limiter.reset_buckets()

    try:
        yield
    finally:
        # 還原
        config.settings.env = old_env
        config.settings.disable_rate_limit = old_disable
        rate_limiter.reset_buckets()


def test_rate_limit_per_ip_returns_429_and_retry_after(client: TestClient, enable_real_rate_limit):
    # 第一次通過
    r1 = client.post("/ask", json={"query": "hello rl"})
    assert r1.status_code == 200

    # 立即第二次 → 429（per_ip_per_min=1, burst=1）
    r2 = client.post("/ask", json={"query": "hello rl again"})
    assert r2.status_code == 429
    assert "Retry-After" in r2.headers


def test_rate_limit_burst_behavior(client: TestClient, enable_real_rate_limit):
    # 調整為：每分鐘配額 1、突發 2 → 前兩次放行、第三次 429
    rate_limiter.configure(per_ip_per_min=1, per_user_per_min=1, burst=2, disabled=False)
    rate_limiter.reset_buckets()

    r1 = client.post("/ask", json={"query": "q1", "user": {"id": "u2"}})
    r2 = client.post("/ask", json={"query": "q2", "user": {"id": "u2"}})
    r3 = client.post("/ask", json={"query": "q3", "user": {"id": "u2"}})

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429
