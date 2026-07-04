# Observability（本機 Prometheus + Grafana）

這個資料夾提供一套 **本機監控環境**，用於觀察 FAQ Bot 與 Agent Governance Policy Gate 的執行情況：

- **Prometheus**：抓取三個來源的指標
- **Grafana**：由 provisioning 自動載入 datasource 與 dashboard，無需手動匯入
- **可選**：將資料 remote_write 到 Grafana Cloud（在 `prometheus.yml` 內已有註解）

---

## 前置需求

- 已安裝 **Docker** 與 **Docker Compose**
- 後端 FastAPI 服務（faq-api）需已在 `http://localhost:8000/metrics` 暴露 Prometheus 指標

---

## 使用方式

### 一鍵啟動

```bash
cd observability
docker-compose up -d
```

啟動後：

- **Prometheus** → http://localhost:9090
- **Grafana** → http://localhost:3000
  - 預設帳密：`admin / admin`
  - 首次登入會要求修改密碼

### Datasource 自動載入

Datasource（Prometheus，uid: `prometheus`）由 `provisioning/datasources/` 自動配置，無需手動設定。

### Dashboard 自動載入

Dashboard 由 `provisioning/dashboards/default.yml` 自動掃描 `dashboards/` 子目錄，啟動後 Grafana 側會出現兩個資料夾：

| Grafana 資料夾 | 來源目錄 | Dashboard |
|---|---|---|
| `governance` | `dashboards/governance/` | Agent Governance — Policy Gate |
| `faq` | `dashboards/faq/` | FAQ Bot Overview v2 |

> `dashboards-archive/` 不在掛載路徑內，Grafana 不再載入其中的舊版 dashboard（faq-bot-overview_v1）。

---

## Prometheus Scrape 來源

三個 scrape 目標：

| 服務 | 位址 | 說明 |
|---|---|---|
| faq-api | `http://host.docker.internal:8000/metrics` | FAQ Bot FastAPI 後端 |
| Pushgateway | `http://pushgateway:9091` | agent-governance-demo 的 Policy Gate 指標（`honor_labels: true`） |
| OPA | `http://opa:8181/metrics` | OPA binary 自身指標（決策延遲等） |

---

## 排練前清場

governance dashboard 為**示意數據**（demo 環境，非生產統計）。排練前可用 agent-governance-demo 的清場腳本清掉舊 schema 殘留：

```bash
cd ../agent-governance-demo
bash scripts/metrics_reset.sh
```

清場後再跑 `bash scripts/run_demo.sh 2 stub` 產資料，確認「累加不倒退」後再上台。

---

## 主要指標（Prometheus metrics）

### FAQ Bot（faq-api）

#### 請求數與延遲
- `llm_requests_total`
- `llm_request_latency_seconds`

#### Token 與成本
- `llm_tokens_total`
- `llm_cost_total_usd_total`

#### 快取相關
- `rag_cache_requests_total`
- `rag_cache_results_total`

#### 子流程延遲
- `rag_embedding_latency_seconds`
- `rag_retrieval_latency_seconds`
- `rag_rerank_latency_seconds`
- `rag_llm_latency_seconds`

#### 輸入檢查 / 限流
- `input_*`

### Agent Governance（Pushgateway，job="agent-governance-demo"）

- `tool_gate_allow_total` / `tool_gate_blocked_total` / `tool_gate_approval_total`
- `tool_gate_audit_event`
- `policy_anomaly_triggered_total`
- `policy_patch_proposed_total` / `policy_patch_accepted_total` / `policy_patch_rejected_total`
- `opa_test_result` / `opa_test_run_total` / `opa_test_duration_seconds`
- `push_time_seconds`（資料新鮮度）

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
```

3. 重新啟動：

```bash
docker compose down
docker compose up -d
```

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
