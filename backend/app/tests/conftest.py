import os
import pytest
from fastapi.testclient import TestClient
from starlette.testclient import TestClient
from app.rate_limit import rate_limiter
from app.main import app
from app.cache import result_cache

rate_limiter.reset_buckets()
# 預設一個 fake key，避免 mock 測試爆掉
os.environ.setdefault("OPENAI_API_KEY", "sk-test-fake")

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def client_no_raise():
    return TestClient(app, raise_server_exceptions=False)

@pytest.fixture(autouse=True)
def _relax_rate_limit_for_tests():
    rate_limiter.configure(per_ip_per_min=10_000, per_user_per_min=10_000, burst=10_000)
    rate_limiter._ip_buckets.clear()
    rate_limiter._user_buckets.clear()
    yield

@pytest.fixture(autouse=True)
def _clear_cache_between_tests():
    # 若你的 result_cache 沒有 clear()，請看下方「補一個 clear()」
    try:
        result_cache.clear()
    except AttributeError:
        # fallback：常見簡易快取都用 dict-like 實作，可加一個屬性或方法
        if hasattr(result_cache, "store") and isinstance(result_cache.store, dict):
            result_cache.store.clear()
    yield
    try:
        result_cache.clear()
    except AttributeError:
        if hasattr(result_cache, "store") and isinstance(result_cache.store, dict):
            result_cache.store.clear()

