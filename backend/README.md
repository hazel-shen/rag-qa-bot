# Day27 - FAQ Bot (RAG + FAISS + OpenAI)

本專案為 **2025 鐵人賽 Day27** 的成果：  
將前面實作的元件整合成一個可 Demo 的 **FAQ Chatbot 雛型**，具備以下能力：

- **API**：`/ask` 問答、`/healthz` 健康檢查、`/metrics` 指標
- **檢索**：FAISS 向量資料庫（持久化）
- **快取**：結果快取（記憶體，可換 Redis）
- **防護**：阻擋內網 URL、SQL Injection
- **觀測**：Prometheus 指標（請求數、延遲、Token 使用量、成本）

---

## 📂 專案結構

```
.
├── README.md
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
├── cloudflare_worker_api_proxy/
│   └── ...                   # Cloudflare Worker Proxy
└── ops/
    └── deploy_container.sh   # 部署腳本
```

---

## 🚀 安裝與環境

### 建立 Conda 環境

```bash
cd backend
conda env create -f environment.yml
conda activate day27_faq_bot
```

### 建立環境變數檔

建立 `.env`（放在 `backend/.env`）：

```env
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

---

## 🔧 Cleaning & Chunking

1. 把原始文件放進 `backend/data/raw/`（支援 `.pdf/.docx/.html/.md/.txt`）
2. 產出 chunks：

```bash
python -m app.ingest.cli_ingest \
  --input backend/data/raw \
  --out backend/data/clean/chunks.jsonl
```

3. 建索引：

```bash
python -m app.build_index --chunks backend/data/clean/chunks.jsonl
```

## 📖 建立 FAISS 索引

| 項目     | 快速模式 (`docs/`)              | 完整模式 (`raw/ → clean/`)                       |
| -------- | ------------------------------- | ------------------------------------------------ |
| 支援格式 | `.txt`, `.md`                   | `.pdf`, `.docx`, `.html`, `.txt`, `.md`          |
| 清洗     | 僅基礎（換行 + 簡單切片）       | 正規化空白、移除頁碼/頁首頁尾、去重              |
| 切片策略 | 固定字元長度                    | 字元長度 + 重疊（保留語意連貫性）                |
| 輸出     | `index.faiss`, `docstore.jsonl` | `chunks.jsonl` → `index.faiss`, `docstore.jsonl` |
| 適用情境 | 快速 Demo / 測試                | 真實場景 / 複雜文件                              |

<br>

提供兩種模式建立索引：

#### 🚀 方式一：快速模式（直接使用 data/docs/）

適用場景： Demo / 測試
支援格式： `.txt` / `.md`
處理方式： 無額外清洗，直接做簡單切片

使用步驟：

1. 準備文件

```bash
# 把文件放進 backend/data/docs/
mkdir -p backend/data/docs
# 例如：
# backend/data/docs/intro.md
# backend/data/docs/faq.txt
```

2. 建立索引

```bash
cd backend
python -m app.build_index --docs backend/data/docs
```

#### 🔧 方式二：完整模式（清洗 + 切片）

適用場景： 真實生產環境
支援格式： .pdf / .docx / .html / .md / .txt
處理方式： 文件清洗（移除頁碼、雜訊）+ 智慧切片

使用步驟：

1. 準備原始文件

```bash
# 建立必要資料夾
mkdir -p backend/data/raw backend/data/clean

# 把原始文件放進 raw/ 資料夾
# 例如：backend/data/raw/intro.pdf
#       backend/data/raw/manual.docx
#       backend/data/raw/website.html
```

2. 執行清洗與切片

```bash
# 清洗並切片，輸出 chunks.jsonl
python -m app.ingest.cli_ingest \
  --input backend/data/raw \
  --out backend/data/clean/chunks.jsonl
```

3. 建立向量索引

```bash
# 使用 chunks.jsonl 建立 FAISS 索引
python -m app.build_index --chunks backend/data/clean/chunks.jsonl
```

---

## 🏃‍♂️ 啟動服務

### 本地啟動 FastAPI

```bash
cd backend
uvicorn app.main:app --reload
```

成功後會有以下端點：

- `GET /healthz` → 健康檢查
- `POST /ask` → 問答 API
- `GET /metrics` → Prometheus 指標

---

## 📡 API 測試

### 問答測試

```bash
curl -s -X POST http://127.0.0.1:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"請簡述 FAQ Bot 的系統架構"}' | jq .
```

### 回傳範例

```json
{
  "answer": "（模型回答內容 ...）",
  "meta": {
    "cached": false,
    "context_preview": "[專案簡介] 這是一個公司內部 FAQ Bot 的示範專案 ...",
    "sources": [
      {
        "id": "...",
        "title": "intro.md",
        "source": "backend/data/docs/intro.md",
        "score": 0.92
      }
    ],
    "usage": { "input_tokens": 123, "output_tokens": 87, "total_tokens": 210 },
    "cost_usd": 0.000045
  }
}
```

---

## 📊 指標 (Prometheus)

服務會暴露 `/metrics`，可收集以下資訊：

| 指標名稱                      | 說明                                  | 類型      |
| ----------------------------- | ------------------------------------- | --------- |
| `llm_requests_total`          | 請求總數（含路由、成功/失敗）         | Counter   |
| `llm_request_latency_seconds` | 請求延遲                              | Histogram |
| `llm_tokens_total`            | LLM Token 使用量（input/output 分開） | Counter   |
| `llm_cost_total_usd`          | LLM API 成本（累積 USD）              | Counter   |

---

## 🛡️ 安全防護

- **內網 URL 阻擋**：`127.0.0.1`, `localhost`, `0.0.0.0`
- **SQL Injection 防護**：`DROP TABLE`, `UNION SELECT` 等關鍵字過濾

---

## 📦 容器化 (選用)

### 建置 Docker Image

```bash
cd backend
docker build -t faq-bot .
```

### 執行容器

```bash
docker run -it --rm -p 8000:8000 \
  -v $(pwd)/data:/app/backend/data \
  --env-file .env \
  faq-bot
```

---

## 🎯 功能特色

### ✅ 已實作功能

- **RAG 檢索**：基於 FAISS 向量相似度搜尋
- **成本控制**：Token 使用量與成本追蹤
- **快取機制**：避免重複查詢的成本
- **監控指標**：Prometheus 格式指標輸出
- **基礎防護**：防止常見安全問題
- **容器化**：支援 Docker 部署

### 🔄 待辦（未來可擴充）

- 將快取改為 Redis
- 更進階的文件清洗與切片策略
- Citation 格式化
- CI/CD 自動建索引 & 部署
- 使用者認證與權限管理
- 多語言支援

---

## 🚀 快速開始

1. **Clone 專案並安裝環境**

   ```bash
   git clone <repo-url>
   cd day27-faq-bot/backend
   conda env create -f environment.yml
   conda activate day27_faq_bot
   ```

2. **設定環境變數**

   ```bash
   cp .env.example .env
   # 編輯 .env，填入你的 OPENAI_API_KEY
   ```

3. **準備文件並建立索引**

   ```bash
   # 把文件放到 backend/data/docs/
   python -m app.build_index
   ```

4. **啟動服務**

   ```bash
   uvicorn app.main:app --reload
   ```

5. **測試問答**
   ```bash
   curl -X POST http://127.0.0.1:8000/ask \
     -H "Content-Type: application/json" \
     -d '{"query":"你的問題"}'
   ```

---

## 📚 相關技術

- **FastAPI**: 現代 Python Web 框架
- **FAISS**: Meta 開源向量搜尋引擎
- **OpenAI API**: GPT 模型與 Embedding
- **Prometheus**: 監控指標收集
- **Docker**: 容器化部署

## 🤝 貢獻

歡迎提交 Issue 或 Pull Request！

## 📄 授權

MIT License
