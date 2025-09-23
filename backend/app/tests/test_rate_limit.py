# app/tests/test_rate_limit.py
from __future__ import annotations

import re
from typing import Optional

import pytest
from starlette.testclient import TestClient

from app.rate_limit import rate_limiter
import app.routes as routes_mod  # 用來關閉 routes 中的 _skip_rate_limit()

def _metric_value(text: str, metric: str, labels: Optional[dict] = None) -> float:
    lines = [ln.strip() for ln in text.splitlines() if ln and not ln.startswith("#")]
    if labels:
        want = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        import re as _re
        pat = _re.compile(rf'^{re.escape(metric)}\{{[^}}]*{re.escape(want)}[^}}]*\}}\s+([0-9.eE+-]+)$')
        for ln in lines:
            m = pat.match(ln)
            if m:
                return float(m.group(1))
        return 0.0
    else:
        import re as _re
        pat = _re.compile(rf'^{re.escape(metric)}\s+([0-9.eE+-]+)$')
        for ln in lines:
            m = pat.match(ln)
            if m:
                return float(m.group(1))
        return 0.0


@pytest.fixture(autouse=True)
def _force_enable_rate_limit(monkeypatch):
    """
    測試中強制啟用速率限制：
    - 讓 routes._skip_rate_limit() 回傳 False（避免 APP_ENV=test 跳過）
    - 重設桶狀態，並設定小配額方便測試
    """
    # 關閉 routes 的「測試環境跳過 RL」邏輯
    monkeypatch.setattr(routes_mod, "_skip_rate_limit", lambda: False, raising=False)
    # 配置小配額並清空桶
    rate_limiter.configure(per_ip_per_min=1, per_user_per_min=1, burst=1, disabled=False)
    rate_limiter.reset_buckets()
    yield
    # 測試後不特別恢復，下一個 fixture 會再設定


def test_rate_limit_per_ip_returns_429_and_retry_after(client: TestClient):
    # 第一次通過
    r1 = client.post("/ask", json={"query": "hello rl"})
    assert r1.status_code == 200

    # 第二次立即打 → 429
    r2 = client.post("/ask", json={"query": "hello rl again"})
    assert r2.status_code == 429
    assert "Retry-After" in r2.headers


def test_rate_limit_per_user_returns_429(client: TestClient):
    # 把 per_user 放寬為 1, burst 1；使用同一 user_id
    rate_limiter.configure(per_ip_per_min=9999, per_user_per_min=1, burst=1, disabled=False)
    rate_limiter.reset_buckets()

    r1 = client.post("/ask", json={"query": "hi"},)
    assert r1.status_code in (200, 429)  # 視上一測試殘留；但我們 reset_buckets() 已清

    r1 = client.post("/ask", json={"query": "hi", "user": {"id": "u1"}})
    assert r1.status_code == 200
    r2 = client.post("/ask", json={"query": "hi again", "user": {"id": "u1"}})
    assert r2.status_code == 429
    assert "Retry-After" in r2.headers


def test_rate_limit_burst_behavior(client: TestClient):
    # 允許兩次突發，第三次 429（每分補 1，不等待）
    rate_limiter.configure(per_ip_per_min=1, per_user_per_min=1, burst=2, disabled=False)
    rate_limiter.reset_buckets()

    r1 = client.post("/ask", json={"query": "q1", "user": {"id": "u2"}})
    r2 = client.post("/ask", json={"query": "q2", "user": {"id": "u2"}})
    r3 = client.post("/ask", json={"query": "q3", "user": {"id": "u2"}})

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429


def test_rate_limit_metrics_increment_on_throttle(client: TestClient):
    # 固定 scope=user 的 429
    rate_limiter.configure(per_ip_per_min=9999, per_user_per_min=1, burst=1, disabled=False)
    rate_limiter.reset_buckets()

    before = client.get("/metrics").text
    m0 = _metric_value(before, "input_rate_limited_total", {"scope": "user"})

    client.post("/ask", json={"query": "hi", "user": {"id": "u3"}})   # pass
    r = client.post("/ask", json={"query": "hi2", "user": {"id": "u3"}})  # throttle
    assert r.status_code == 429

    after = client.get("/metrics").text
    m1 = _metric_value(after, "input_rate_limited_total", {"scope": "user"})
    assert m1 == m0 + 1
