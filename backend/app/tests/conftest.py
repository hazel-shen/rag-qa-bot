import os
import pytest
from fastapi.testclient import TestClient
from app.main import app

# 預設一個 fake key，避免 mock 測試爆掉
os.environ.setdefault("OPENAI_API_KEY", "sk-test-fake")

@pytest.fixture
def client():
    return TestClient(app)
