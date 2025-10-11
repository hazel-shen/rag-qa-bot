# app/tests/conftest.py
import os
import sys
import pytest
from unittest.mock import MagicMock, Mock, patch
from fastapi.testclient import TestClient
from app.rate_limit import rate_limiter
from app.cache import result_cache
import app.config as config

# 0) 只有「一般單元測試」才補假金鑰；e2e / ingest / eval / perf 一律不補
@pytest.fixture(autouse=True)
def _fake_key_for_unit_tests(request, monkeypatch):
    if any(request.node.get_closest_marker(m) for m in ("e2e", "ingest", "perf", "eval")):
        return
    # 若外部未設定,才補上假的
    if not os.environ.get("OPENAI_API_KEY"):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake")


# 1) 測試用 TestClient
@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)

@pytest.fixture
def client_no_raise():
    from app.main import app
    return TestClient(app, raise_server_exceptions=False)

# 2) 全域打樁：避免打到 OpenAI（必要）
#    但若 RAG_DISABLE_STUB=1 或者 test 有 @pytest.mark.eval / @pytest.mark.e2e / @pytest.mark.perf,就完全不打樁
@pytest.fixture(autouse=True)
def _stub_llm(monkeypatch, request):
    # 先檢查是否要跳過 stub
    if any(request.node.get_closest_marker(m) for m in ("e2e", "ingest", "perf", "eval")):
        return

    # 🔧 關鍵修正：直接 mock app.llm.answer_with_context 函數
    # 而不是 mock OpenAI client
    def mock_answer_with_context(query: str, context):
        return {
            "text": f"Mock LLM response for: {query[:50]}",
            "usage": {
                "input_tokens": 100,
                "output_tokens": 50, 
                "total_tokens": 150
            },
            "cost_usd": 0.001
        }
    
    # 確保 app.llm 被導入
    import app.llm as llm_module
    monkeypatch.setattr(llm_module, "answer_with_context", mock_answer_with_context)
    
    # 如果 llm 模組有 _client 屬性，設為 None 避免真實初始化
    if hasattr(llm_module, "_client"):
        monkeypatch.setattr(llm_module, "_client", None)
    
    # Mock app.routes._retrieve_candidates 避免依賴 FAISS
    def mock_retrieve_candidates(query, k):
        return [
            {
                "id": "mock-doc-1",
                "title": "Mock Document 1",
                "text": "This is mock document 1",
                "source": "mock1.txt",
                "score": 0.9
            },
            {
                "id": "mock-doc-2",
                "title": "Mock Document 2",
                "text": "This is mock document 2",
                "source": "mock2.txt",
                "score": 0.8
            }
        ]
    
    try:
        import app.routes as routes_module
        monkeypatch.setattr(routes_module, "_retrieve_candidates", mock_retrieve_candidates)
    except:
        pass

    # Mock reranker 
    def fake_rerank(query, cands):
        for i, c in enumerate(cands):
            c["reranker_score"] = 1.0 - i * 0.01
        return cands[:]
    
    try:
        import app.reranker as reranker_module
        monkeypatch.setattr(reranker_module, "rerank", fake_rerank)
    except:
        pass

# 3) 一般測試：放寬限流（自動套用）
@pytest.fixture(autouse=True)
def _relax_rate_limit_for_tests():
    rate_limiter.configure(per_ip_per_min=10_000, per_user_per_min=10_000, burst=10_000, disabled=False)
    rate_limiter.reset_buckets()
    yield
    rate_limiter.reset_buckets()


# 4) 每個測試前後清空快取
@pytest.fixture(autouse=True)
def _clear_cache_between_tests():
    try:
        result_cache.clear()
    except AttributeError:
        if hasattr(result_cache, "store") and isinstance(result_cache.store, dict):
            result_cache.store.clear()
    yield
    try:
        result_cache.clear()
    except AttributeError:
        if hasattr(result_cache, "store") and isinstance(result_cache.store, dict):
            result_cache.store.clear()


# 5) 需要「真的測限流」時使用這個 fixture（在測試函式參數列出）
@pytest.fixture
def enable_real_rate_limit():
    old_env = getattr(config.settings, "env", "")
    old_disable = getattr(config.settings, "disable_rate_limit", False)

    # 讓 routes._skip_rate_limit() 不跳過
    config.settings.env = "dev"              # 不要是 "test"
    config.settings.disable_rate_limit = False

    # 設定小額度以便觸發 429
    rate_limiter.configure(per_ip_per_min=1, per_user_per_min=1, burst=1, disabled=False)
    rate_limiter.reset_buckets()
    yield
    # 還原
    config.settings.env = old_env
    config.settings.disable_rate_limit = old_disable
    rate_limiter.reset_buckets()

# 6) Mock FAISS index,避免單元測試依賴實際檔案
@pytest.fixture(autouse=True)
def mock_faiss_index(monkeypatch, request):
    """自動 mock FAISS index,但 e2e/ingest/perf/eval 測試除外"""
    if any(request.node.get_closest_marker(m) for m in ("e2e", "ingest", "perf", "eval")):
        return
    
    # 直接 mock routes.py 中的 _retrieve_candidates
    def mock_retrieve_candidates(query, k):
        return [
            {
                "id": "mock-doc-1",
                "title": "Mock Document 1",
                "text": "This is mock document 1",
                "source": "mock1.txt",
                "score": 0.9
            },
            {
                "id": "mock-doc-2",
                "title": "Mock Document 2",
                "text": "This is mock document 2",
                "source": "mock2.txt",
                "score": 0.8
            }
        ]
    
    # 同時 mock retrieval 層的函數
    def mock_load_index():
        pass
    
    def mock_search(query, k):
        return [("mock-doc-1", 0.9), ("mock-doc-2", 0.8)]
    
    def mock_retrieve_topk(query, k):
        return mock_retrieve_candidates(query, k)
    
    try:
        import app.routes as routes_module
        monkeypatch.setattr(routes_module, "_retrieve_candidates", mock_retrieve_candidates)
    except:
        pass
    
    try:
        import app.retrieval as retrieval_module
        monkeypatch.setattr(retrieval_module, "load_index", mock_load_index)
        monkeypatch.setattr(retrieval_module, "search", mock_search)
        monkeypatch.setattr(retrieval_module, "retrieve_topk", mock_retrieve_topk)
    except:
        pass