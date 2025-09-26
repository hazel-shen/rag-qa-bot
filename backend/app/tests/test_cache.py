# tests/test_cache.py
import pytest

from app.cache import result_cache
from app.config import settings

def test_result_cache_set_get_roundtrip():
    key = "ask:unit-cache-test"
    payload = {"answer": "hello", "meta": {"cached": False}}
    result_cache.set(key, payload)
    got = result_cache.get(key)
    assert got["answer"] == "hello"
    assert got["meta"]["cached"] is False


def test_cache_hit_same_query_same_setting(client, mocker):
    # 首次：寫入快取
    mocker.patch("app.retrieval.retrieve_topk", return_value=[{
        "id":"c1","title":"Doc1","text":"aaa","source":"s1","score":0.9
    }])
    mocker.patch("app.routes.rerank", return_value=[{
        "id":"c1","title":"Doc1","text":"aaa","source":"s1",
        "score":0.9,"reranker_score":0.9
    }])
    mocker.patch("app.llm.answer_with_context", return_value={
        "text":"A","usage":{},"cost_usd":0.0
    })

    r1 = client.post("/ask", json={"query": "same-key"})
    assert r1.status_code == 200
    assert r1.json()["meta"]["cached"] is False

    r2 = client.post("/ask", json={"query": "same-key"})
    assert r2.status_code == 200
    assert r2.json()["meta"]["cached"] is True


def test_cache_miss_when_setting_changes(client, mocker, monkeypatch):
    """
    現在 _cache_key_for_query() 會把 settings.top_k / chat_model / rerank_model / index_version
    都納入 key。修改任一設定後，同樣的 query 應該要「不命中」。
    這裡示範修改 top_k；也可以改 chat_model/rerank_model 做同樣驗證。
    """
    # 先固定住管線行為
    mocker.patch("app.retrieval.retrieve_topk", return_value=[{
        "id":"c1","title":"Doc1","text":"aaa","source":"s1","score":0.9
    }])
    mocker.patch("app.routes.rerank", return_value=[{
        "id":"c1","title":"Doc1","text":"aaa","source":"s1",
        "score":0.9,"reranker_score":0.9
    }])
    mocker.patch("app.llm.answer_with_context", return_value={
        "text":"A","usage":{},"cost_usd":0.0
    })

    query = "setting-key"

    # 第一次：用目前的 settings.top_k
    r1 = client.post("/ask", json={"query": query})
    assert r1.status_code == 200
    assert r1.json()["meta"]["cached"] is False

    # 修改設定（直接改 settings 物件的屬性，因為 routes 也是拿這個單例）
    # 方式一：改 top_k，應該形成不同的快取 key
    monkeypatch.setattr(settings, "top_k", settings.top_k + 2, raising=False)

    r2 = client.post("/ask", json={"query": query})
    assert r2.status_code == 200
    assert r2.json()["meta"]["cached"] is False

    # （可選）方式二：再改 chat_model，也應該 miss
    monkeypatch.setattr(settings, "chat_model", settings.chat_model + "-alt", raising=False)
    r3 = client.post("/ask", json={"query": query})
    assert r3.status_code == 200
    assert r3.json()["meta"]["cached"] is False
