# Day27 - FAQ Bot (RAG + FAISS + OpenAI)

本專案為 2025 鐵人賽 Day27 的成果：將前面實作的元件整合成一個可 Demo 的 FAQ Chatbot 雛型，具備以下能力：

- **API**：`/ask` 問答、`/healthz` 健康檢查、`/metrics` 指標
- **檢索**：FAISS 向量資料庫（持久化）
- **快取**：結果快取（記憶體，可換 Redis）
- **防護**：阻擋內網 URL、SQL Injection
- **觀測**：Prometheus 指標（請求數、延遲、Token 使用量、成本）

## 📂 專案結構

```yaml
./
├── backend/                        # 後端服務 (FastAPI + RAG pipeline)
│ ├── app/                          # 核心程式碼 (檢索、重排序、快取、防護、API)
│ ├── data/                         # 測試/開發用資料 (raw / clean / docs)
│ ├── benchmark/                    # 壓測腳本 (ab / locust)
│ └── tests/                        # 測試案例 (pytest)
├── frontend/                       # 前端靜態頁面 (index.html + JS + CSS)
├── observability/                  # 監控配置 (Prometheus + Grafana)
├── cloudflare_worker_api_proxy/    # Cloudflare Worker Proxy
├── ops/                            # 部署腳本
├── docker-compose.yml              # 本地開發編排
└── README.md                       # 專案說明文件
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

把原始文件放進 `backend/data/raw/`（支援 .pdf/.docx/.html/.md/.txt）。
這些檔案會先經過 Loader，依副檔名選擇對應的解析方式（例如 PDF 用 PyMuPDF，DOCX 用 python-docx，HTML 用 BeautifulSoup），最後統一轉換成純文字，再進行清洗與切片。

執行：

```bash
python -m app.ingest.cli_ingest \
  --input ./data/raw \
  --out ./data/clean/chunks.jsonl
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
python -m app.build_index --docs ./data/docs
```

完整模式：

```bash
python -m app.build_index \
  --chunks ./data/clean/chunks.jsonl \
  --docstore ./data/docs/docstore.jsonl \
  --index ./data/docs/index.faiss
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

回答品質測試（打真的 OpenAI API，有成本 ⚠️）：

```bash
pytest -m eval -s -vv
```

## 🛡️ 安全防護

- 阻擋內網 URL（127.0.0.1 / localhost）
- SQL Injection 關鍵字過濾
- 輸入長度限制

## 🎯 功能特色

- RAG 檢索 + 重排 (FAISS + OpenAI)
- 文件清洗與切片 (Ingest pipeline)
- 成本追蹤與快取機制
- Prometheus 指標收集
- Docker 容器化部署

## 🔄 待辦 (未來)

- 壓測數據（證明 p95 ≤3s、QPS ≥3）(Day02)
- 正確性檢查（用一小份 dataset 驗證回答合理性）-> 做完了，可是準率可以更好
- 實作員工/部門？
- 更進階的清洗/切片策略
- Citation 格式化
- CI/CD 自動建索引與部署
- 使用者認證與權限管理
