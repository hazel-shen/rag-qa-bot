#!/usr/bin/env sh
# bench_latency.sh
# 用途：用壓力測試來測試程式含 rerank 的延遲。

set -eu

# ===== 可調參數（也可用環境變數覆蓋） =====
API_URL="${API_URL:-http://127.0.0.1:8000/ask?nocache=1}"
QS_FILE="${QS_FILE:-benchmark/bench_queries.txt}"  # 查詢清單（每行一題）
OUT_PREFIX="${OUT_PREFIX:-local}"         # 輸出檔名前綴
WARMUP="${WARMUP:-3}"                     # 預熱請求數
LIMIT_N="${LIMIT_N:-50}"                  # 正式量測筆數
TIMEOUT="${TIMEOUT:-60}"                  # 單筆最大等待秒數（curl --max-time）

# ===== 依賴檢查 =====
need() { command -v "$1" >/dev/null 2>&1 || { echo "缺少指令：$1"; exit 127; }; }
need curl
need jq
need python3

[ -f "$QS_FILE" ] || { echo "queries file not found: $QS_FILE"; exit 1; }

# ===== 預熱（確保路徑與本機模型都被觸發載入） =====
echo "== [Local Rerank] warm-up x$WARMUP =="
i=1
while [ "$i" -le "$WARMUP" ]; do
  curl -s -X POST "$API_URL" \
    -H 'Content-Type: application/json' \
    -H 'X-Cache-Bypass: 1' \
    --max-time "$TIMEOUT" \
    -d '{"query":"請列出系統包含哪些檔案格式？（warmup）"}' \
    -o /dev/null || true
  i=$((i+1))
done

# ===== 清空輸出檔 =====
: > "${OUT_PREFIX}_lat.txt"
: > "${OUT_PREFIX}_log.txt"

echo "== [Local Rerank] sequential $LIMIT_N requests =="

# ===== 主迴圈：逐行送出、顯示進度、記錄延遲與 HTTP Code =====
count=0
# 用 awk 取前 N 行，避免檔案比 N 長
awk "NR<=${LIMIT_N}" "$QS_FILE" | \
while IFS= read -r q || [ -n "$q" ]; do
  [ -z "$q" ] && continue
  count=$((count+1))
  printf '\n[%02d/%d] sending...\n' "$count" "$LIMIT_N"

  # 送出請求；失敗時以 "TIMEOUT" 標記，time 設為 TIMEOUT 秒
  resp=$(
    curl -s -X POST "$API_URL" \
      -H 'Content-Type: application/json' \
      -H 'X-Cache-Bypass: 1' \
      --max-time "$TIMEOUT" \
      -d "$(jq -n --arg q "$q" '{query:$q}')" \
      -w '%{time_total} %{http_code}\n' \
      -o /dev/null \
    || printf '%s TIMEOUT\n' "$TIMEOUT"
  )

  # 解析兩個欄位：time_total 與 http_code（或 TIMEOUT）
  # 用 set -- 來拆欄位
  # shellcheck disable=SC2086
  set -- $resp
  time_total="$1"
  http_code="${2:-TIMEOUT}"

  # 寫檔
  printf '%s\n' "$time_total" >> "${OUT_PREFIX}_lat.txt"
  printf '[%02d] %s | %s\n' "$count" "$time_total" "$http_code" >> "${OUT_PREFIX}_log.txt"

  # 進度列印
  printf 'progress: %d/%d (last=%ss code=%s)\r' "$count" "$LIMIT_N" "$time_total" "$http_code"
done

echo
echo "== [Local Rerank] stats (n=${LIMIT_N}) =="

# ===== 用 Python 計算 p50 / p95 與 ok/bad =====
python3 - "${OUT_PREFIX}_lat.txt" "${OUT_PREFIX}_log.txt" <<'PY'
import sys, math
lat_file, log_file = sys.argv[1], sys.argv[2]

xs=[]
for l in open(lat_file,'r',encoding='utf-8'):
    l=l.strip()
    if l:
        try: xs.append(float(l))
        except: pass

def pct(a,q):
    if not a: return float('nan')
    a=sorted(a); k=(len(a)-1)*(q/100)
    f=math.floor(k); c=math.ceil(k)
    return a[int(k)] if f==c else a[f]+(a[c]-a[f])*(k-f)

ok=bad=0
for l in open(log_file,'r',encoding='utf-8'):
    l=l.strip()
    if not l: continue
    tok=l.split()[-1]
    try:
        code=int(tok)
        if 200<=code<300: ok+=1
        else: bad+=1
    except:
        bad+=1

print(f"n={len(xs)} ok={ok} bad={bad}")
print(f"p50={pct(xs,50):.4f}s  p95={pct(xs,95):.4f}s")
PY
