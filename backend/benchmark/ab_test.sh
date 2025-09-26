#!/usr/bin/env bash
# ab_test.sh
# 用途：用 ApacheBench 來做壓力測試。
set -euo pipefail

URL="${URL:-http://127.0.0.1:8000/ask}"
DATA='{"query":"系統架構有哪些元件？"}'   # 對應 architecture.md
TOTAL="${TOTAL:-100}"   # 總請求數
CONC="${CONC:-20}"      # 併發數

echo "POST $TOTAL requests (c=$CONC) to $URL"
ab -n "$TOTAL" -c "$CONC" -p <(echo "$DATA") -T "application/json" "$URL"
