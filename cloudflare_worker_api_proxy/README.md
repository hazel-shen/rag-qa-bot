建立 Cloudflare Worker 作為後端 API 反向代理伺服器

在前端 Cloudflare Pages 與後端 EC2 / Container Service 之間，我們不直接暴露後端，而是透過 Cloudflare Worker 做一層反向代理（Reverse Proxy）。這樣可以：

✅ 統一流量入口，讓 API 與前端在同一網域下工作

✅ 加上安全控管（CORS、Header 驗證、Access 驗證）

✅ 利用 Cloudflare Edge 的低延遲節點，提升體驗

架構設計

最簡化的正式線上路徑：

Cloudflare Pages (前端)
↓
Cloudflare Worker (反向代理)
↓
Cloudflare Tunnel (安全隧道)
↓
EC2 / Container (後端 API)

Worker：公開的 API 入口，處理 CORS、驗證標頭、轉發流量

Tunnel：不直接暴露 EC2 公網 IP，而是透過 cloudflared 建立安全隧道

Backend：只接受來自 Worker 的請求（例如驗證 X-From-Worker header）

建立流程

1. 安裝與初始化

```bash
   npm install -g wrangler
   wrangler init api-proxy
```

選擇 Application Starter 或 API starter 模板。

2. 設定 wrangler.jsonc

指定入口檔案與環境變數：

```json
{
  "name": "api-proxy",
  "main": "src/index.ts",
  "compatibility_date": "2025-09-20",
  "vars": {
    "TARGET_BASE_URL": "https://api-internal.yourdomain.com",
    "WORKER_SHARED_SECRET": "supersecret123"
  }
}
```

3. 撰寫 Worker 程式

一個簡單的反向代理（CORS + Header 驗證）`src/index.ts`

4. 部署 Worker
   wrangler deploy

部署完成後，會得到一個公開的 \*.workers.dev 或綁定的自訂域名。

```bash
❯ wrangler deploy

 ⛅️ wrangler 4.38.0
───────────────────
Total Upload: 24.77 KiB / gzip: 6.02 KiB
Worker Startup Time: 14 ms
Your Worker has access to the following bindings:
Binding                                          Resource
env.TARGET_BASE_URL ("https://httpbin.org")      Environment Variable

Uploaded api-proxy (3.27 sec)
Deployed api-proxy triggers (0.86 sec)
  https://${你的專案名稱}.xxxx.workers.dev
Current Version ID: b885fXXXX
```

## 安全控制

🔒 CORS Policy：只允許來自指定 Pages 網域的請求
🔑 Header Validation：後端驗證 X-From-Worker 標頭，確保請求來自 Worker
🛡️ Cloudflare Tunnel：避免後端暴露公網，所有流量走隧道
🔐 Access (Zero Trust)（進階）：可以要求 Worker 必須附帶 JWT/Access Token 才能存取

這樣 Worker 就成為 後端唯一入口，既能做安全檢查，又能保持架構乾淨。
