#!/usr/bin/env sh
# cost_bench.sh
# 用途：用壓力測試來測試每個 query 的 token 花費
set -eu

# ==== 可調參數（也可用環境變數覆蓋） ====
API_URL="${API_URL:-http://127.0.0.1:8000/ask?nocache=1}"
N_SAMPLES="${N_SAMPLES:-100}"
NT_RATE="${NT_RATE:-32}"                    # 匯率 NTD/USD
QS_FILE="${QS_FILE:-benchmark/cost_queries.txt}"
OUT_FILE="${OUT_FILE:-benchmark/cost_result.jsonl}"
SRC_JSONL="${SRC_JSONL:-app/tests/data/eval_small.jsonl}"
TIMEOUT="${TIMEOUT:-60}"                    # 單請求最大等待秒數

need() { command -v "$1" >/dev/null 2>&1 || { echo "缺少指令：$1"; exit 127; }; }
need curl
need python3
# jq 可選；有就用 jq 匯總，沒有就用 Python 匯總
HAS_JQ=0
command -v jq >/dev/null 2>&1 && HAS_JQ=1

[ -f "$SRC_JSONL" ] || { echo "找不到資料集：$SRC_JSONL"; exit 1; }

# ==== 1) 產生 100 題（允許重複） ====
python3 - <<PY "$SRC_JSONL" "$QS_FILE" "$N_SAMPLES"
import json, random, sys, pathlib
src, outp, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
qs = [json.loads(l)["question"] for l in open(src, encoding="utf-8") if l.strip()]
random.seed()
with open(outp,"w",encoding="utf-8") as f:
    for _ in range(n):
        f.write(random.choice(qs) + "\n")
print(f"[gen] wrote {n} queries to {outp}")
PY

# ==== 2) 逐筆送出，累積結果 ====
: > "$OUT_FILE"
ok=0; bad=0; i=0
echo "== [Cost Bench] sequential ${N_SAMPLES} requests (nocache) =="
while IFS= read -r q || [ -n "$q" ]; do
  [ -z "$q" ] && continue
  i=$((i+1))
  printf '\n[%03d/%d] sending...\n' "$i" "$N_SAMPLES"

  # 組 JSON body（用 python 確保正確跳脫）
  BODY=$(python3 - <<'PY' "$q"
import json, sys
print(json.dumps({"query": sys.argv[1]}, ensure_ascii=False))
PY
  )

  # 送出；失敗時補一行 {"_error": "..."} 以便統計
  resp=$(
    curl -s -X POST "$API_URL" \
      -H 'Content-Type: application/json' \
      -H 'X-Cache-Bypass: 1' \
      --max-time "$TIMEOUT" \
      -d "$BODY"
  ) || true

  # 嘗試擷取 http code：用額外呼叫帶 -o /dev/null，不影響 resp
  code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API_URL" \
      -H 'Content-Type: application/json' \
      -H 'X-Cache-Bypass: 1' \
      --max-time "$TIMEOUT" \
      -d "$BODY") || code="000"

  if [ "$code" -ge 200 ] 2>/dev/null && [ "$code" -lt 300 ] 2>/dev/null; then
    ok=$((ok+1))
    printf '%s\n' "$resp" >> "$OUT_FILE"
  else
    bad=$((bad+1))
    printf '%s\n' "${resp:-{\"_error\":\"HTTP_$code\"}}" >> "$OUT_FILE"
  fi
  printf 'progress: %d/%d (code=%s)\r' "$i" "$N_SAMPLES" "$code"
done < "$QS_FILE"
echo
echo "[done] ok=$ok bad=$bad -> $OUT_FILE"

# ==== 3) 匯總 ====
if [ "$HAS_JQ" -eq 1 ]; then
  # 使用 jq 匯總（容錯：缺欄位時當 0）
  TOTAL_USD=$(jq -rs '[.[]|.meta.cost_usd // 0] | add' "$OUT_FILE")
  TOTAL_TOK=$(jq -rs '[.[]|(.meta.token_usage.total // .meta.usage.total_tokens // 0)] | add' "$OUT_FILE")
  LE300=$(jq -rs '[.[]|(.meta.token_usage.total // .meta.usage.total_tokens // 0) | select(.>0 and .<=300)] | length' "$OUT_FILE")
else
  # 用 Python 匯總
  read -r TOTAL_USD TOTAL_TOK LE300 <<EOF
$(python3 - <<'PY' "$OUT_FILE"
import sys, json
usd=toks=le300=0.0
n=0
for l in open(sys.argv[1],encoding='utf-8'):
    l=l.strip()
    if not l: continue
    try:
        o=json.loads(l)
    except:
        continue
    n+=1
    meta=o.get("meta",{})
    usd += float(meta.get("cost_usd",0) or 0)
    # 兩種可能欄位：token_usage.total 或 usage.total_tokens
    tu = (meta.get("token_usage",{}) or {}).get("total")
    if tu is None:
        tu = (meta.get("usage",{}) or {}).get("total_tokens")
    tu = float(tu or 0)
    toks += tu
    if 0 < tu <= 300: le300 += 1
print(f"{usd} {toks} {int(le300)}")
PY
)
EOF
fi

# 基本指標
N=$(wc -l < "$QS_FILE" | tr -d ' ')
[ "$N" -gt 0 ] || { echo "N=0"; exit 1; }

python3 - <<PY "$N" "$NT_RATE" "$TOTAL_USD" "$TOTAL_TOK" "$ok" "$bad" "$OUT_FILE" "$QS_FILE"
import sys, json, math, statistics, pathlib
N=int(sys.argv[1]); rate=float(sys.argv[2])
total_usd=float(sys.argv[3]); total_tok=float(sys.argv[4])
ok=int(sys.argv[5]); bad=int(sys.argv[6])
outf=sys.argv[7]; qf=sys.argv[8]

avg_usd = total_usd / N
avg_ntd = avg_usd * rate
avg_tok = (total_tok / N) if N else float('nan')

print("==== Cost Summary ====")
print(f"queries_file    : {qf}")
print(f"results_file    : {outf}")
print(f"n/ok/bad        : {N}/{ok}/{bad}")
print(f"fx (NTD/USD)    : {rate}")
print(f"total_usd       : {total_usd:.6f}")
print(f"avg_usd         : {avg_usd:.6f}")
print(f"avg_ntd         : {avg_ntd:.3f}")
print(f"avg_tokens      : {avg_tok:.1f}")

# 驗收：avg_ntd < 0.2
print(f"ACCEPT(avg_ntd<0.2): {'PASS' if avg_ntd < 0.2 else 'FAIL'}")
PY

# 額外：如要看 ≤300 tokens 的占比（若用 jq 匯總）
if [ "$HAS_JQ" -eq 1 ]; then
  pct=$(python3 - <<PY "$LE300" "$N"
import sys
le300=int(sys.argv[1]); n=int(sys.argv[2])
print(f"{le300/n*100:.1f}")
PY
)
  echo "pct(total_tokens ≤ 300): ${pct}%"
fi
