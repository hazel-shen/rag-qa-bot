# Day27 - FAQ Bot (RAG + FAISS + OpenAI)

本專案為 2025 鐵人賽 Day27 的成果。
將前面實作的元件整合成一個可 Demo 的 FAQ Chatbot 雛型，具備以下能力：

- **API**：`/ask` 問答、`/healthz` 健康檢查、`/metrics` 指標
- **檢索**：FAISS 向量資料庫（持久化）
- **快取**：結果快取（記憶體，可換 Redis）
- **防護**：阻擋內網 URL、SQL Injection
- **觀測**：Prometheus 指標（請求數、延遲、Token 使用量、成本）

## 專案架構

```mermaid
flowchart TB
  %% 使用者
  U((使用者)):::user -->|送出問題| API[FastAPI /ask]:::api

  %% API 層
  subgraph API_Layer[API 層]
    style API_Layer fill:#e0f2fe,stroke:#0369a1,stroke-width:2px
    API --> GUARD_DEC{輸入是否合法？}:::decision
    GUARD_DEC -->|否：阻擋| BLOCK[回傳錯誤]:::process
    GUARD_DEC -->|是：繼續| RL[速率限制]:::process
    RL --> CACHE_DEC{快取命中？}:::decision
  end

  CACHE_DEC -->|是：回傳快取| RESP[回應]:::process
  CACHE_DEC -->|否：查詢| RET[FAISS 檢索器]:::process

  %% 檢索與生成
  subgraph Pipeline[檢索與生成流程]
    style Pipeline fill:#ede9fe,stroke:#6d28d9,stroke-width:2px
    RET -->|候選文件| RER[重排序器以及建構上下文]:::process
    RER -->|產生提示| LLM[LLM]:::llm
  end
  LLM -->|寫入快取| CACHE[結果快取]:::cache
  CACHE -->|提供答案| RESP
  RESP -->|回傳| API
  API -->|回覆| U

  %% 文件管線
  subgraph Ingest[文件管線-離線處理]
    style Ingest fill:#fef9c3,stroke:#ca8a04,stroke-width:2px
    RAW[原始文件]:::ingest --> CLEAN[清洗]:::ingest --> CHUNK[切片]:::ingest --> INDEX[向量索引]:::ingest
  end
  INDEX -->|提供索引| RET

  %% 觀測
  subgraph Obs[觀測]
    style Obs fill:#fce7f3,stroke:#be185d,stroke-width:2px
    METRICS[Prometheus 指標<br/>QPS / 延遲 / Token / 成本 / 快取命中率]:::metrics
  end
  API -->|紀錄| METRICS
  CACHE -->|紀錄| METRICS
  RET -->|紀錄| METRICS
  RER -->|紀錄| METRICS
  LLM -->|紀錄| METRICS

  %% 配色
  classDef user fill:#d1fae5,stroke:#10b981,stroke-width:2px;
  classDef api fill:#bfdbfe,stroke:#2563eb,stroke-width:2px;
  classDef decision fill:#fde68a,stroke:#d97706,stroke-width:2px;
  classDef process fill:#f3f4f6,stroke:#374151,stroke-width:2px;
  classDef llm fill:#fecaca,stroke:#dc2626,stroke-width:2px;
  classDef cache fill:#bbf7d0,stroke:#16a34a,stroke-width:2px;
  classDef metrics fill:#f9a8d4,stroke:#be185d,stroke-width:2px;
  classDef ingest fill:#fef3c7,stroke:#b45309,stroke-width:2px;
```

## 專案結構

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

## 啟動方式

詳見各個子資料夾的 `README.md`。

### conda 小抄

```bash
conda env create -f environment.yaml
conda activate dayXX_XXX

# 停用環境
conda deactivate

# 查看所有環境
conda env list

# 刪除環境（⚠️ 慎用）
conda env remove -n dayXX_XXX

# 更新環境（當 environment.yml 有修改時）
conda env update -f environment.yml --prune
```
