# app/tests/test_e2e.py
# 會真的打到 OpenAI API，注意 token 成本
import pytest
import uuid
import re

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
    assert len(data["answer"]) > 0

    # meta 檢查
    meta = data.get("meta", {})
    assert "sources" in meta
    assert isinstance(meta["sources"], list)
    assert len(meta["sources"]) > 0

    # usage 與成本檢查
    assert "usage" in meta
    assert "cost_usd" in meta
    assert isinstance(meta["cost_usd"], float)

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

