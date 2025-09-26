# Observability（本機 Prometheus + Grafana）

這個資料夾提供一套 **本機監控環境**，用於觀察 FAQ Bot 的執行情況：

- **Prometheus**：抓取後端 `/metrics`（FastAPI 服務）
- **Grafana**：內建一個「FAQ Bot Overview」儀表板（JSON 可匯入）
- **可選**：將資料 **remote_write 到 Grafana Cloud**（在 `prometheus.yml` 內已有註解）

---

## 前置需求

- 已安裝 **Docker** 與 **Docker Compose**
- 後端 FastAPI 服務需已在 [http://localhost:8000/metrics](http://localhost:8000/metrics) 暴露 Prometheus 指標

---

## 使用方式

### 一鍵啟動

```bash
cd observability
docker compose up -d
```

啟動後：

- **Prometheus** → http://localhost:9090
- **Grafana** → http://localhost:3000
  - 預設帳密：`admin / admin`
  - 首次登入會要求修改密碼

### 設定 Prometheus Data Source

首次登入 Grafana 後：

1. 進入 **Connections** → **Data Sources**
2. 新增 **Prometheus**
3. URL 填入：`http://prometheus:9090`  
   （因為 Grafana 與 Prometheus 在同一個 docker compose 網路中）

> 若登入後已自動帶入 Prometheus Data Source，可略過這一步。

### 匯入儀表板

1. **Grafana** → **Dashboards** → **Import**
2. 上傳 `dashboards/faq-bot-overview.json`
3. 匯入完成後會看到 **FAQ Bot Overview** 儀表板

---

## 主要指標（Prometheus metrics）

FAQ Bot 服務會輸出以下常用指標：

### 請求數與延遲

- `llm_requests_total`
- `llm_request_latency_seconds`

### Token 與成本

- `llm_tokens_total`
- `llm_cost_total_usd_total`

### 快取相關

- `rag_cache_requests_total`
- `rag_cache_results_total`

### 子流程延遲

- `rag_embedding_latency_seconds`
- `rag_retrieval_latency_seconds`
- `rag_rerank_latency_seconds`
- `rag_llm_latency_seconds`

### 輸入檢查 / 限流

- `input_*`

---

## （可選）送資料到 Grafana Cloud

1. 到 Grafana Cloud 建立 Prometheus → 複製 remote_write endpoint、Basic Auth User、API Key

2. 開啟 `prometheus.yml`，將 `remote_write` 段落取消註解並填入：

```yaml
remote_write:
  - url: https://prometheus-<stack-id>.grafana.net/api/prom/push
    basic_auth:
      username: "<instance id or user>"
      password: "<grafana cloud api key>"
    write_relabel_configs:
      - source_labels: [job]
        target_label: job
        replacement: "faq-bot-dev"
```

3. 重新啟動：

```bash
docker compose down
docker compose up -d
```

**建議**：用不同 job/label 區分 dev 與 prod，避免資料混在一起。

**注意**：Grafana Cloud Free Plan 保留時間為 14 天，remote_write 會增加流量與存放量。

---

## 關閉 / 清除資料

```bash
docker compose down
```

若要清空 Prometheus/Grafana 的本機資料卷：

```bash
docker volume rm observability_prom_data observability_grafana_data
```

⚠️ **如果要保留 Grafana 的儀表板配置，不要刪除 `grafana_data` volume。**

## 📊 指標 (Prometheus)

| 分類         | 指標                                                                                                                                                                 | 說明                 |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------- |
| Runtime      | `python_gc_*`, `python_info`                                                                                                                                         | Python GC 與版本資訊 |
| 請求         | `llm_requests_total`, `llm_request_latency_seconds`                                                                                                                  | 請求數、延遲統計     |
| Token/成本   | `llm_tokens_total`, `llm_cost_total_usd_total`                                                                                                                       | Token 使用量與成本   |
| Cache        | `rag_cache_requests_total`, `rag_cache_results_total`                                                                                                                | Cache 查詢與命中率   |
| RAG Pipeline | `rag_embedding_latency_seconds`, `rag_retrieval_latency_seconds`, `rag_rerank_latency_seconds`, `rag_llm_latency_seconds`, `rag_errors_total`                        | 各階段延遲與錯誤     |
| Input Policy | `input_accepted_total`, `input_rejected_total`, `input_rate_limited_total`, `input_chars_histogram`, `input_tokens_histogram`, `input_violation_last_seen_timestamp` | 輸入檢查與限流統計   |
