# bench_throughput.py
# 用途：測試程式的吞吐量，並且記錄成報告
import csv, pathlib

stats = pathlib.Path("benchmark/locust_cache_stats.csv")
rows = list(csv.DictReader(stats.open()))
reqs = [r for r in rows if r["Name"] and r["Name"] != "Aggregated"]
total = sum(int(r["Request Count"]) for r in reqs)
fails = sum(int(r["Failure Count"]) for r in reqs)

hist = pathlib.Path("benchmark/locust_cache_stats_history.csv")
hist_rows = list(csv.DictReader(hist.open())) if hist.exists() else []

if hist_rows:
    try:
        t0 = int(float(hist_rows[0]["Timestamp"]))
        t1 = int(float(hist_rows[-1]["Timestamp"]))
        duration = max(1, t1 - t0)  # 確保不為 0
    except ValueError:
        # 萬一 Timestamp 不是數字才 fallback
        duration = 60
else:
    duration = 60

qps = total / duration if duration else 0.0
fail_pct = (fails / total * 100.0) if total else 0.0

print("==== Throughput Summary ====")
print(f"total_requests={total}")
print(f"duration_s={duration}")
print(f"avg_qps={qps:.2f}")
print(f"failure_rate={fail_pct:.2f}%")
print("ACCEPT(QPS≥3 & fail<1%):", "PASS" if (qps>=3 and fail_pct<1) else "FAIL")
