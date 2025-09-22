import pytest

@pytest.mark.e2e
def test_ask_real(client):
    resp = client.post("/ask", json={"query": "FAQ Bot 的系統架構是什麼？"})
    assert resp.status_code == 200
    data = resp.json()

    # 驗證回傳至少有 answer 與來源
    assert "answer" in data
    assert "sources" in data["meta"]
    assert len(data["meta"]["sources"]) > 0
    # 這裡會真的打到 OpenAI API，注意 token 成本
