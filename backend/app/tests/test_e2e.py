# app/tests/test_e2e.py
# 會真的打到 OpenAI API，注意 token 成本

# ✅ 在任何匯入/fixture 之前，最早關掉 stub
import os
os.environ["RAG_DISABLE_STUB"] = "1"

import uuid
import re
import pytest
import importlib


# ------------------------------------------------------------
# 本檔自帶 client fixture（不依賴外部 conftest 的 client）
# ------------------------------------------------------------
@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


# ------------------------------------------------------------
# 強制走 OpenAI：檢查金鑰、調整設定、還原被 monkeypatch 的 llm
# ------------------------------------------------------------
@pytest.fixture(autouse=True)
def _force_real_openai_for_e2e(monkeypatch):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key or api_key == "sk-test-fake":
        pytest.skip("需要真實 OPENAI_API_KEY；否則略過 E2E。")

    # 1) 設定金鑰/環境與保險參數
    from app.config import settings
    settings.openai_api_key = api_key
    settings.env = "test"
    if hasattr(settings, "disable_rate_limit"):
        settings.disable_rate_limit = True

    if not getattr(settings, "chat_model", None):
        settings.chat_model = "gpt-4o-mini"
    if not getattr(settings, "answer_max_tokens", None) or settings.answer_max_tokens < 128:
        settings.answer_max_tokens = 256
    if hasattr(settings, "answer_single_line"):
        settings.answer_single_line = False

    # 2) 關掉 clean_answer（no-op）
    try:
        import app.routes as routes_mod
        def _no_clean(s: str, single_line: bool = False) -> str:
            return (s or "").strip()
        monkeypatch.setattr(routes_mod, "clean_answer", _no_clean, raising=True)
    except Exception:
        pass

    # 3) 還原 llm 模組，避免先前被 autouse monkeypatch 汙染
    import app.llm as llm_mod
    llm_mod = importlib.reload(llm_mod)

    # 4) 包一層 answer_with_context：列印 raw/usage，幫助除錯
    try:
        from app.config import settings as _s
        _orig_answer = llm_mod.answer_with_context

        def _wrapped_answer_with_context(query: str, context):
            print(f"[e2e-debug] calling LLM model={getattr(_s, 'chat_model', None)} "
                  f"max_tokens={getattr(_s, 'answer_max_tokens', None)} "
                  f"stub_disabled={os.environ.get('RAG_DISABLE_STUB')}")
            out = _orig_answer(query, context)
            raw = (out.get("text") or "")
            usage = out.get("usage") or {}
            print(f"[e2e-debug] LLM raw head: {raw[:120]!r}")
            print(f"[e2e-debug] usage: {usage} cost={out.get('cost_usd')}")
            return out

        monkeypatch.setattr(llm_mod, "answer_with_context", _wrapped_answer_with_context, raising=True)

        # 重置 LLM client（若你的 llm 模組有這個全域）
        if hasattr(llm_mod, "_client"):
            llm_mod._client = None
    except Exception:
        pass

    # 5) 關掉本檔快取，避免命中舊值
    try:
        import app.routes as routes_mod
        class _NoCache:
            def get(self, *a, **k): return None
            def set(self, *a, **k): return None
        monkeypatch.setattr(routes_mod, "result_cache", _NoCache(), raising=True)
    except Exception:
        pass


# ------------------------------------------------------------
# 測試內容
# ------------------------------------------------------------
@pytest.mark.e2e
def test_ask_real(client):
    """E2E: 測試 /ask 端點，完整走到 OpenAI API"""
    query = f"FAQ Bot 的系統架構是什麼？ ({uuid.uuid4()})"
    resp = client.post("/ask", json={"query": query})
    assert resp.status_code == 200
    data = resp.json()

    # 基本結構
    assert "answer" in data
    assert isinstance(data["answer"], str)
    if not data["answer"]:
        print("\n[debug-meta]", data.get("meta"))
    assert len(data["answer"]) > 0

    # meta 檢查
    meta = data.get("meta", {})
    assert "sources" in meta and isinstance(meta["sources"], list) and len(meta["sources"]) > 0
    assert "usage" in meta and "cost_usd" in meta and isinstance(meta["cost_usd"], float)


@pytest.mark.e2e
def test_healthz(client):
    """E2E: 健康檢查"""
    resp = client.get("/healthz")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "ok"


@pytest.mark.e2e
def test_metrics(client):
    """E2E: Prometheus 指標輸出"""
    resp = client.get("/metrics")
    assert resp.status_code == 200
    text = resp.text

    # 至少要有這幾個核心指標
    assert "llm_requests_total" in text
    assert "llm_request_latency_seconds" in text
    assert "llm_tokens_total" in text

    # 檢查 Prometheus 格式
    assert re.search(r"^llm_requests_total\{.*\}\s+\d+", text, re.M)
