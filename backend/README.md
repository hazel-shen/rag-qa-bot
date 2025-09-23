# Day27 - FAQ Bot (RAG + FAISS + OpenAI)

本專案為 2025 鐵人賽 Day27 的成果：將前面實作的元件整合成一個可 Demo 的 FAQ Chatbot 雛型，具備以下能力：

- **API**：`/ask` 問答、`/healthz` 健康檢查、`/metrics` 指標
- **檢索**：FAISS 向量資料庫（持久化）
- **快取**：結果快取（記憶體，可換 Redis）
- **防護**：阻擋內網 URL、SQL Injection
- **觀測**：Prometheus 指標（請求數、延遲、Token 使用量、成本）

## 📂 專案結構

```yaml
.
├── backend/
│   ├── environment.yml       # Conda 環境
│   ├── Dockerfile            # 容器化 (Micromamba)
│   ├── app/
│   │   ├── main.py           # FastAPI 入口
│   │   ├── routes.py         # API routes (/ask, /healthz)
│   │   ├── security.py       # 基礎防護
│   │   ├── observability.py  # Prometheus 指標
│   │   ├── cache.py          # 結果快取
│   │   ├── retrieval.py      # FAISS 檢索
│   │   ├── reranker.py       # 文件重排
│   │   ├── llm.py            # OpenAI Chat 回答 + 成本統計
│   │   ├── config.py         # 設定 (環境變數)
│   │   └── ingest/           # 清洗 + 切片模組
│   │       ├── loaders.py
│   │       ├── cleaning.py
│   │       ├── chunking.py
│   │       └── cli_ingest.py
│   └── data/
│       ├── raw/              # 原始文件 (pdf/docx/html/md/txt)
│       ├── clean/            # 清洗 + 切片後輸出 (chunks.jsonl)
│       ├── docs/             # 快速模式文件 (txt/md)
│       ├── index.faiss       # FAISS 索引 (build 後產出)
│       └── docstore.jsonl    # 文件中繼資料 (build 後產出)
├── frontend/                 # 前端 (簡單網頁)
│   └── index.html
├── benchmark/                # 壓測腳本 (ab/locust)
├── ops/                      # 部署腳本
│   └── deploy_container.sh
└── pytest.ini                # 測試標記設定
```

## 🚀 安裝與環境

```bash
cd backend
conda env create -f environment.yml
conda activate day27_faq_bot
```

建立 .env：

```plaintext
OPENAI_API_KEY=sk-xxxx
EMBED_MODEL=text-embedding-3-small
CHAT_MODEL=gpt-4o-mini
DATA_DIR=backend/data
INDEX_PATH=backend/data/index.faiss
DOCSTORE_PATH=backend/data/docstore.jsonl
TOP_K=3
MAX_CONTEXT_CHARS=1800
ANSWER_MAX_TOKENS=400
```

## 🔧 文件清洗 & 切片

把原始文件放進 backend/data/raw/（支援 .pdf/.docx/.html/.md/.txt）
清洗 + 切片：

```bash
python -m app.ingest.cli_ingest \
  --input backend/data/raw \
  --out backend/data/clean/chunks.jsonl
```

輸出：

```bash
backend/data/clean/chunks.jsonl → 切片後的語料
```

## 📖 建立 FAISS 索引

提供兩種模式：

| 項目     | 快速模式 (`docs/`)              | 完整模式 (`raw/ → clean/`)                       |
| -------- | ------------------------------- | ------------------------------------------------ |
| 支援格式 | `.txt`, `.md`                   | `.pdf`, `.docx`, `.html`, `.txt`, `.md`          |
| 清洗     | 簡單換行切分                    | 正規化空白、移除頁碼、去重                       |
| 輸出     | `index.faiss`, `docstore.jsonl` | `chunks.jsonl` → `index.faiss`, `docstore.jsonl` |

快速模式：

```bash
python -m app.build_index --docs backend/data/docs
```

完整模式：

```bash
python -m app.build_index --chunks backend/data/clean/chunks.jsonl
```

## 🏃‍♂️ 啟動服務

```bash
cd backend
uvicorn app.main:app --reload
```

端點：

- GET /healthz → 健康檢查
- POST /ask → 問答 API
- GET /metrics → Prometheus 指標

## 📡 API 測試

```bash
curl -s -X POST http://127.0.0.1:8000/ask \
 -H "Content-Type: application/json" \
 -d '{"query":"請簡述 FAQ Bot 的系統架構"}'
```

## 🧪 測試策略

專案使用 pytest，並透過 pytest.ini 管理標記：

```plaintext
addopts = -m "not e2e and not perf"

markers =
  e2e: end-to-end 測試，會打 OpenAI API ⚠️
  perf: 效能測試，本地 mock，測 QPS/延遲
```

執行方式：

- 單元測試 (預設)：

```bash
pytest -v
```

E2E 測試（打真的 OpenAI API，有成本 ⚠️）：

```bash
pytest -m e2e -v
```

效能測試 (mock)：

```bash
pytest -m perf -v
```

## 📊 指標 (Prometheus)

| 分類         | 指標                                                                                                                                                                 | 說明                 |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------- |
| Runtime      | `python_gc_*`, `python_info`                                                                                                                                         | Python GC 與版本資訊 |
| 請求         | `llm_requests_total`, `llm_request_latency_seconds`                                                                                                                  | 請求數、延遲統計     |
| Token/成本   | `llm_tokens_total`, `llm_cost_total_usd_total`                                                                                                                       | Token 使用量與成本   |
| Cache        | `rag_cache_requests_total`, `rag_cache_results_total`                                                                                                                | Cache 查詢與命中率   |
| RAG Pipeline | `rag_embedding_latency_seconds`, `rag_retrieval_latency_seconds`, `rag_rerank_latency_seconds`, `rag_llm_latency_seconds`, `rag_errors_total`                        | 各階段延遲與錯誤     |
| Input Policy | `input_accepted_total`, `input_rejected_total`, `input_rate_limited_total`, `input_chars_histogram`, `input_tokens_histogram`, `input_violation_last_seen_timestamp` | 輸入檢查與限流統計   |

## 🛡️ 安全防護

- 阻擋內網 URL（127.0.0.1 / localhost）
- SQL Injection 關鍵字過濾
- 輸入長度限制

## ✅ 驗收標準 (Day02)

- 延遲：p95 ≤ 3 秒
- 吞吐量：QPS ≥ 3
- 正確性：FAQ 問答正確率達基本要求

目前已達成 Demo 驗收條件。

## 🎯 功能特色

- RAG 檢索 + 重排 (FAISS + OpenAI)
- 文件清洗與切片 (Ingest pipeline)
- 成本追蹤與快取機制
- Prometheus 指標收集
- Docker 容器化部署

## 🔄 待辦 (未來)

- Redis 快取
- 回答格式改善 (Day2 驗收)
- 加上使用者介面 (Day2 驗收)
- Metrics 傳到本機的 Grafana 並且可以畫圖 (Day2 驗收)
- 更進階的清洗/切片策略
- Citation 格式化
- CI/CD 自動建索引與部署
- 使用者認證與權限管理
