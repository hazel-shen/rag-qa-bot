# locustfile_with_cache.py
# 用途：開啟快取並且做壓力測試
from locust import HttpUser, task, between
import random, json, pathlib, uuid, os

HOT_FILE = pathlib.Path("benchmark/hot_queries.txt")
COLD_FILE = pathlib.Path("benchmark/bench_queries.txt")
HOT = [q.strip() for q in HOT_FILE.read_text(encoding="utf-8").splitlines() if q.strip()] if HOT_FILE.exists() else []
COLD = [q.strip() for q in COLD_FILE.read_text(encoding="utf-8").splitlines() if q.strip()] if COLD_FILE.exists() else []

# 熱流量比例，可用環境變數覆蓋：HOT_RATIO=0.95
HOT_RATIO = float(os.getenv("HOT_RATIO", "0.95"))

class RAGUser(HttpUser):
    # 模擬人類擊鍵節奏；需要更高 QPS 可調小
    wait_time = between(0.05, 0.20)

    def on_start(self):
        # 每位使用者一個唯一 user_id（方便後端觀測與避免某些 per-user 快取/限流衝突）
        self.user_id = str(uuid.uuid4())

    @task
    def ask(self):
        # 依 HOT_RATIO 選擇熱/冷查詢
        use_hot = (random.random() < HOT_RATIO) and len(HOT) > 0
        bank = HOT if use_hot else (COLD if COLD else HOT)
        q = random.choice(bank)

        body = {"query": q, "user_id": self.user_id}
        # 注意：不加 ?nocache=1、不帶 X-Cache-Bypass，讓快取命中
        self.client.post(
            "/ask",
            headers={"Content-Type": "application/json"},
            data=json.dumps(body, ensure_ascii=False),
            name="/ask (cached)"
        )
