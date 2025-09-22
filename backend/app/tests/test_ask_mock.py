def test_ask_with_mocked_llm(client, mocker):
    # 模擬 LLM 回覆
    fake_answer = {"text": "mocked answer", "usage": {}, "cost_usd": 0.0}
    mocker.patch("app.llm.answer_with_context", return_value=fake_answer)

    # 模擬 retrieval 結果
    fake_cands = [
        {"id": "c1", "title": "doc1", "text": "hello world", "source": "raw/doc1", "score": 0.9}
    ]
    mocker.patch("app.retrieval.retrieve_topk", return_value=fake_cands)
    mocker.patch("app.reranker.rerank", return_value=fake_cands)

    resp = client.post("/ask", json={"query": "test query"})
    assert resp.status_code == 200
    data = resp.json()

    # 驗證回傳
    assert data["answer"] == "mocked answer"
    assert data["meta"]["cached"] is False
    assert data["meta"]["sources"][0]["id"] == "c1"
