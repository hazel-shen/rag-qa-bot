# crash_bench.sh
# 用途：殺掉 APP 並重啟，測試復原速度
URL=http://127.0.0.1:8000/healthz
PID=12158

START=$(date +%s)
kill -9 $PID    # 模擬 crash

# 立刻重新啟動一個 uvicorn (模擬 systemd/docker-compose 幫你拉起)
uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 &

# 等待健康檢查成功
until curl -sf "$URL" >/dev/null; do sleep 0.5; done
END=$(date +%s)

echo "cold start = $((END-START))s"
