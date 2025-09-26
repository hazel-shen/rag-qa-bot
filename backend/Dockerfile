# ── Base ──────────────────────────────────────────────────────────────────────
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# 科學運算常見依賴（FAISS/NumPy）
RUN apt-get update && apt-get install -y --no-install-recommends \
      libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── 固定 UID/GID，避免主機掛載目錄的權限問題 ────────────────────────────────
ARG APP_UID=10001
ARG APP_GID=10001
RUN groupadd -g $APP_GID appuser && useradd -m -u $APP_UID -g $APP_GID appuser

# 先安裝依賴（仍以 root 進行）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製程式；可直接用 --chown 減少後續 chown 成本（需要較新 Docker 版本）
COPY --chown=appuser:appuser app ./app

# 建立資料目錄並調整權限（同時把 /app 也交給非 root）
RUN mkdir -p /data && chown -R appuser:appuser /data /app

# 切換為非 root
USER appuser

# ── 預設環境參數 ────────────────────────────────────────────────────────────
ENV APP_ENV=dev \
    PORT=8080 \
    HEALTH_PATH=/healthz \
    LOG_LEVEL=info \
    WORKERS=2

EXPOSE 8080

# ── 健康檢查 ─────────────────────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD python - <<'PY' || exit 1
import urllib.request, os, sys
port=os.getenv("PORT","8080")
path=os.getenv("HEALTH_PATH","/healthz")
try:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=2) as r:
        sys.exit(0 if r.status==200 else 1)
except Exception:
    sys.exit(1)
PY

# ── Gunicorn + UvicornWorker 啟動 ────────────────────────────────────────────
CMD ["bash","-lc","exec gunicorn -k uvicorn.workers.UvicornWorker -w ${WORKERS:-2} -b 0.0.0.0:${PORT:-8080} app.main:app --log-level ${LOG_LEVEL:-info}"]
