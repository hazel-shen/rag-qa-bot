# app/tests/test_reranker.py
import types
import pytest
import app.reranker as mod  # 被測：mod.rerank()

class _FakeCE:
    """可注入的 CrossEncoder 假物件；predict() 依測試場景回傳分數或丟例外。"""
    def __init__(self, scores=None, boom=False, capture=False):
        self._scores = scores or []
        self._boom = boom
        self.capture = capture
        self.captured_pairs = None
        self.captured_kwargs = None

    def predict(self, pairs, **kwargs):
        if self.capture:
            self.captured_pairs = pairs
            self.captured_kwargs = kwargs
        if self._boom:
            raise RuntimeError("boom")
        # 若未提供分數，就按長度產生遞減分數，確保可排序
        if not self._scores:
            return [float(len(pairs) - i) for i in range(len(pairs))]
        # 截到與 pairs 等長
        return self._scores[: len(pairs)]

def test_rerank_empty_list(monkeypatch):
    """空候選應直接回空（不呼叫模型）。"""
    fake = _FakeCE(scores=[])
    monkeypatch.setattr(mod, "_CE", fake, raising=True)
    out = mod.rerank("hello", [])
    assert out == []

def test_rerank_orders_by_score(monkeypatch):
    """依 CrossEncoder 分數排序，並帶回 reranker_score。"""
    # 3 個候選，分數讓索引 1 最高、再來 0、最後 2
    fake = _FakeCE(scores=[0.8, 0.95, 0.5])
    monkeypatch.setattr(mod, "_CE", fake, raising=True)

    cands = [
        {"id": "d0", "title": "t0", "text": "aaa", "source": "s0", "score": 0.50},
        {"id": "d1", "title": "t1", "text": "bbb", "source": "s1", "score": 0.60},
        {"id": "d2", "title": "t2", "text": "ccc", "source": "s2", "score": 0.70},
    ]
    out = mod.rerank("q", cands)
    # 依 0.95 > 0.8 > 0.5 排序
    assert [o["id"] for o in out] == ["d1", "d0", "d2"]
    assert "reranker_score" in out[0]
    assert out[0]["reranker_score"] == pytest.approx(0.95, rel=1e-6)

def test_rerank_respects_top_k(monkeypatch):
    """最多只返回 settings.top_k 個。"""
    monkeypatch.setattr(mod.settings, "top_k", 2, raising=False)
    fake = _FakeCE(scores=[0.8, 0.95, 0.5])
    monkeypatch.setattr(mod, "_CE", fake, raising=True)

    cands = [
        {"id": "d0", "title": "t0", "text": "aaa", "source": "s0", "score": 0.5},
        {"id": "d1", "title": "t1", "text": "bbb", "source": "s1", "score": 0.6},
        {"id": "d2", "title": "t2", "text": "ccc", "source": "s2", "score": 0.7},
    ]
    out = mod.rerank("q", cands)
    assert len(out) == 2
    # 分數 0.95 最大的是 index=1（id=d1）
    assert [o["id"] for o in out] == ["d1", "d0"]

def test_rerank_fallback_on_exception(monkeypatch):
    """模型拋錯時回退到原始前 top_k，且 reranker_score 為 None。"""
    monkeypatch.setattr(mod.settings, "top_k", 2, raising=False)
    fake = _FakeCE(boom=True)
    monkeypatch.setattr(mod, "_CE", fake, raising=True)

    cands = [
        {"id": "d0", "title": "t0", "text": "aaa", "source": "s0", "score": 0.9},
        {"id": "d1", "title": "t1", "text": "bbb", "source": "s1", "score": 0.8},
        {"id": "d2", "title": "t2", "text": "ccc", "source": "s2", "score": 0.7},
    ]
    out = mod.rerank("q", cands)
    assert [o["id"] for o in out] == ["d0", "d1"]     # 原始順序的前 top_k
    assert out[0].get("reranker_score") is None

def test_rerank_truncates_text(monkeypatch):
    """確認輸入給模型的 (query, text) 有套用長度限制（例如 1000 chars）。"""
    # 啟用 capture 以檢查送入的 pairs
    fake = _FakeCE(scores=[0.5, 0.4], capture=True)
    monkeypatch.setattr(mod, "_CE", fake, raising=True)

    long_text = "X" * 5000
    cands = [
        {"id": "d0", "title": "t0", "text": long_text, "source": "s0", "score": 0.5},
        {"id": "d1", "title": "t1", "text": "short",     "source": "s1", "score": 0.6},
    ]
    out = mod.rerank("q", cands)
    assert len(out) == 2
    assert fake.captured_pairs is not None
    # pairs: [(query, text_truncated), ...]
    q0, t0 = fake.captured_pairs[0]
    assert q0 == "q"
    assert len(t0) <= 1000    # 依你在 reranker.py 的截斷長度調整
