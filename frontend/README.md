# 🎨 前端開發啟動

專案內建一個簡單的靜態網頁（frontend/index.html），提供輸入問題 → 呼叫後端 API → 顯示答案的功能。

## 1. 本機啟動方式

使用任何靜態伺服器工具：

Python:

```bash
cd frontend
python -m http.server 8080
```

Node.js (serve):

```bash
npm install -g serve
serve -l 8080
```

2. 瀏覽器存取

打開 http://localhost:8080，即可看到 FAQ Bot 頁面。
輸入問題後，前端會呼叫後端 API：

- POST http://127.0.0.1:8000/ask
- GET http://127.0.0.1:8000/healthz (健康檢查)
