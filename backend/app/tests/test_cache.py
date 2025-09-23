from app.cache import result_cache

def test_result_cache_set_get_roundtrip():
    key = "ask:unit-cache-test"
    payload = {"answer": "hello", "meta": {"cached": False}}
    result_cache.set(key, payload)
    got = result_cache.get(key)
    assert got["answer"] == "hello"
    assert got["meta"]["cached"] is False

import pytest
from app.cache import result_cache

def test_cache_hit_same_query_same_setting(client, mocker):
    # 首次：寫入快取
    mocker.patch("app.retrieval.retrieve_topk", return_value=[{
        "id":"c1","title":"Doc1","text":"aaa","source":"s1","score":0.9
    }])
    mocker.patch("app.routes.rerank", return_value=[{
        "id":"c1","title":"Doc1","text":"aaa","source":"s1","score":0.9,"reranker_score":0.9
    }])
    mocker.patch("app.llm.answer_with_context", return_value={"text":"A","usage":{},"cost_usd":0.0})

    r1 = client.post("/ask", json={"query": "same-key"})
    assert r1.status_code == 200
    assert r1.json()["meta"]["cached"] is False

    r2 = client.post("/ask", json={"query": "same-key"})
    assert r2.status_code == 200
    assert r2.json()["meta"]["cached"] is True

#TODO
@pytest.mark.xfail(reason="目前 cache key 未納入設定；待 _cache_key_for_query 納入 top_k/chat_model 後再啟用")
def test_cache_miss_when_setting_changes(client, mocker, monkeypatch):
    # 第一次用預設 TOP_K
    mocker.patch("app.retrieval.retrieve_topk", return_value=[{
        "id":"c1","title":"Doc1","text":"aaa","source":"s1","score":0.9
    }])
    mocker.patch("app.routes.rerank", return_value=[{
        "id":"c1","title":"Doc1","text":"aaa","source":"s1","score":0.9,"reranker_score":0.9
    }])
    mocker.patch("app.llm.answer_with_context", return_value={"text":"A","usage":{},"cost_usd":0.0})

    r1 = client.post("/ask", json={"query": "setting-key"})
    assert r1.json()["meta"]["cached"] is False

    # 改變 TOP_K，理想行為：cache key 應不同 → 不命中
    monkeypatch.setenv("TOP_K", "5")
    # 若 settings 是在 import 時固定，可在程式中提供 reload；此處略過，示意預期行為
    r2 = client.post("/ask", json={"query": "setting-key"})
    assert r2.json()["meta"]["cached"] is False
