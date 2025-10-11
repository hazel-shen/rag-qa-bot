# FAQ Bot 系統架構設計

## 整體流程

1. 使用者透過前端輸入問題
2. 問題經過向量化（Embedding）
3. 系統到向量資料庫檢索相似片段
4. 檢索到的內容會被拼接進 Prompt
5. 大語言模型 (LLM) 生成回答
6. 回答回傳給使用者

## 元件細節

### 前端 (Frontend)

- 提供使用者輸入框與回覆區域
- 可內嵌在內部 Portal
- 與 Backend API 溝通

### 後端 (Backend FastAPI)

- 提供 `/ask` API
- 健康檢查端點 `/healthz`
- 指標端點 `/metrics`
- 整合快取、檢索與 LLM

### 向量資料庫 (FAISS)

- 採用 L2 正規化後的內積檢索
- 儲存文件清洗與切片後的片段
- 提供 Top-k 查詢

### 大語言模型 (LLM)

- 使用 OpenAI GPT-4o-mini
- 控制回答長度與溫度參數
- 回答中可引述來源

### 觀測 (Observability)

- 使用 Prometheus
- 指標包含：
  - llm_requests_total
  - llm_request_latency_seconds
  - llm_tokens_total
  - llm_cost_total_usd
