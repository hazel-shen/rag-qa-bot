// web/config.js
// 1) 本機同網域部署（nginx 反代 /ask 到後端） → 留空字串 ""（走相對路徑）
// 2) 本機跨網域 / Cloudflare Pages → 設定完整 URL，例如：
//    "http://127.0.0.1:8000" 或 "https://your-api.example.com"
window.APP_CONFIG = {
  BACKEND_URL: "",
  ASK_PATH: "/api/ask",
  HEALTHZ_PATH: "/api/healthz"
};
