# app/tests/test_input_limits.py
from __future__ import annotations

import re
import time
from typing import Optional
import pytest

from app.security import load_policy
from starlette.testclient import TestClient
from unittest.mock import Mock

@pytest.fixture(autouse=True)
def ensure_llm_mock(monkeypatch):
    """確保 LLM 被正確 mock，避免真的打 OpenAI"""
    # Mock answer_with_context 函數
    mock_response = {
        "text": "Mock response for input validation test",
        "usage": {
            "input_tokens": 10,
            "output_tokens": 5,
            "total_tokens": 15
        },
        "cost_usd": 0.0001
    }
    
    import app.llm
    monkeypatch.setattr(app.llm, "answer_with_context", lambda q, ctx: mock_response)
    
    # 也 mock _retrieve_candidates 避免依賴 FAISS
    import app.routes
    def mock_retrieve(query, k):
        return [
            {"id": "test-1", "title": "Test", "text": "Test content", "source": "test.txt", "score": 0.9}
        ]
    monkeypatch.setattr(app.routes, "_retrieve_candidates", mock_retrieve)


def _metric_value(text: str, metric: str, labels: Optional[dict] = None) -> float:
    """
    超輕量的 Prometheus 文本解析器：抓取單一 metric 當前值。
    支援 metric{label="x"} 形式；若 labels=None，則匹配無標籤行。
    """
    lines = [ln.strip() for ln in text.splitlines() if ln and not ln.startswith("#")]
    if labels:
        # 轉成如 {type="format",scope="user"} 的順序不敏感匹配
        want = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        pat = re.compile(rf'^{re.escape(metric)}\{{[^}}]*{re.escape(want)}[^}}]*\}}\s+([0-9.eE+-]+)$')
        for ln in lines:
            m = pat.match(ln)
            if m:
                return float(m.group(1))
        return 0.0
    else:
        pat = re.compile(rf'^{re.escape(metric)}\s+([0-9.eE+-]+)$')
        for ln in lines:
            m = pat.match(ln)
            if m:
                return float(m.group(1))
        return 0.0


def test_length_bounds_pass_and_reject(client: TestClient):
    policy = load_policy()
    max_chars = int((policy.get("length") or {}).get("max_chars", 2000))

    # < 上限：通過
    r = client.post("/ask", json={"query": "hello"})
    assert r.status_code == 200

    # = 上限：通過
    r = client.post("/ask", json={"query": "a" * max_chars})
    assert r.status_code == 200

    # > 上限：拒絕（400，type=length）
    before = client.get("/metrics").text
    before_rej = _metric_value(before, "input_rejected_total", {"type": "length"})
    r = client.post("/ask", json={"query": "a" * (max_chars + 1)})
    assert r.status_code == 400
    j = r.json()
    assert j["meta"]["type"] == "length"
    after = client.get("/metrics").text
    after_rej = _metric_value(after, "input_rejected_total", {"type": "length"})
    assert after_rej == before_rej + 1


def test_format_rejects_script_and_codeblock(client: TestClient):
    # HTML/script
    r = client.post("/ask", json={"query": "<script>alert(1)</script>"})
    assert r.status_code == 400
    assert r.json()["meta"]["type"] == "format"

    # code block / shell pipeline
    r = client.post("/ask", json={"query": "```rm -rf /```"})
    assert r.status_code == 400
    assert r.json()["meta"]["type"] == "format"

    r = client.post("/ask", json={"query": "ls | grep txt || rm -rf /"})
    assert r.status_code == 400
    assert r.json()["meta"]["type"] == "format"


def test_blacklist_keywords_and_regex(client: TestClient):
    # 關鍵字：SQL
    r = client.post("/ask", json={"query": "DROP TABLE users;"})
    assert r.status_code == 400
    assert r.json()["meta"]["type"] == "keyword"

    # IMDS：可能被歸類 url 或 regex，兩者皆可
    r = client.post("/ask", json={"query": "http://169.254.169.254/latest/meta-data"})
    assert r.status_code == 400
    assert r.json()["meta"]["type"] in ("url", "regex")


def test_url_rejected_when_not_allowed(client: TestClient):
    # 預設 allow_urls=false
    r = client.post("/ask", json={"query": "see http://example.com/docs/1"})
    assert r.status_code == 400
    assert r.json()["meta"]["type"] == "url"


def test_metrics_increment_on_accept_and_reject(client: TestClient):
    before = client.get("/metrics").text
    acc0 = _metric_value(before, "input_accepted_total")
    rej0 = _metric_value(before, "input_rejected_total", {"type": "format"})

    # 一次通過
    r = client.post("/ask", json={"query": "正常問題"})
    assert r.status_code == 200

    # 一次拒絕（format）
    r = client.post("/ask", json={"query": "<iframe src=x onerror=alert(1)>"})
    assert r.status_code == 400
    assert r.json()["meta"]["type"] == "format"

    after = client.get("/metrics").text
    acc1 = _metric_value(after, "input_accepted_total")
    rej1 = _metric_value(after, "input_rejected_total", {"type": "format"})

    assert acc1 == acc0 + 1
    assert rej1 == rej0 + 1
