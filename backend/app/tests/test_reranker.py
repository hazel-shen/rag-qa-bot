import types
from app.reranker import rerank

class _FakeRerankObj:
    def __init__(self, data):
        self.data = data

class _FakeItem:
    def __init__(self, index, score):
        self.index = index
        self.score = score

class _FakeClient:
    def __init__(self, results):
        self._results = results
        self.rerank = types.SimpleNamespace(
            create=lambda **kwargs: _FakeRerankObj(self._results)
        )

def test_rerank_empty_list(monkeypatch):
    # 空候選應直接回空
    out = rerank("hello", [])
    assert out == []

def test_rerank_orders_by_score(monkeypatch):
    # 準備假的 API 結果（把原本 cands 的索引 1 放前面）
    fake_results = [
        _FakeItem(index=1, score=0.91),
        _FakeItem(index=0, score=0.80),
    ]
    from app import reranker as mod
    monkeypatch.setattr(mod, "_client", _FakeClient(fake_results))

    cands = [
        {"id": "d0", "title": "t0", "text": "aaa", "source": "s0", "score": 0.5},
        {"id": "d1", "title": "t1", "text": "bbb", "source": "s1", "score": 0.6},
    ]
    out = rerank("q", cands)
    assert [o["id"] for o in out] == ["d1", "d0"]
    assert "reranker_score" in out[0]
