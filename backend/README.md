# Backend

## 前置條件

| 工具 | 說明 |
| ---- | ---- |
| conda | 管理 Python 環境 |
| Git LFS | raw data 用 LFS 管理，未安裝會 ingest 到指標字串而非真實內容 |
| Docker（選用） | 僅使用 Redis cache 時需要 |
| jq（選用） | 美化 curl 輸出用 |

```bash
brew install git-lfs jq   # macOS
git lfs install && git lfs pull
```

## 快速開始

**1. 建立環境**

```bash
cd backend
conda env create -f environment.yaml
conda activate rag_qa_bot
```

**2. 建立 `.env`**（路徑以 `backend/` 為基準）

```plaintext
OPENAI_API_KEY=sk-xxxx
EMBED_MODEL=text-embedding-3-small
CHAT_MODEL=gpt-5.4-mini
DATA_DIR=./data
INDEX_PATH=./data/index.faiss
DOCSTORE_PATH=./data/docstore.jsonl
TOP_K=3
MAX_CONTEXT_CHARS=1800
ANSWER_MAX_TOKENS=400
CACHE_BACKEND=memory
```

> `gpt-5.4-mini`（及更新的 reasoning 系列）使用 `max_completion_tokens`，已在 `llm.py` 處理，換回舊模型不需額外修改。

**3. Ingest & 建索引**（在 `backend/` 下執行，會呼叫 Embedding API）

```bash
python -m app.ingest.cli_ingest --input ./data/raw --out ./data
python -m app.build_index \
  --chunks ./data/clean/chunks.jsonl \
  --docstore ./data/docstore.jsonl \
  --index ./data/index.faiss
```

**4. 啟動服務**

```bash
uvicorn app.main:app --reload --port 8000
```

## 端點

| 端點 | 說明 |
| ---- | ---- |
| `GET /healthz` | 健康檢查 |
| `POST /ask` | 問答 API |
| `GET /metrics` | Prometheus 指標 |

## API 測試

```bash
# 完整回應
curl -s -X POST http://127.0.0.1:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"請簡述 FAQ Bot 的系統架構"}' | jq .

# 只看回答
curl -s -X POST http://127.0.0.1:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"請簡述 FAQ Bot 的系統架構"}' | jq -r '.answer'
```

## Cache

| 模式 | CACHE_BACKEND | 說明 |
| ---- | ------------- | ---- |
| 記憶體（預設） | `memory` | 無需額外服務，重啟後清空 |
| Redis | `redis` | 需先啟動 Redis，重啟後資料保留 |

使用 Redis 時，先在專案根目錄啟動：

```bash
docker compose up redis -d   # 從 rag-qa-bot/ 執行
```

> ⚠️ `CACHE_BACKEND=redis` 但 Redis 未啟動時，`/ask` 會回傳 500。

## 測試

| 指令 | 說明 |
| ---- | ---- |
| `pytest -v` | 單元測試（預設） |
| `pytest -m e2e -v` | E2E 測試，打真實 OpenAI API ⚠️ |
| `pytest -m perf -v` | 效能測試（mock） |
| `pytest -m eval -s -vv` | 回答品質測試，打真實 OpenAI API ⚠️ |
