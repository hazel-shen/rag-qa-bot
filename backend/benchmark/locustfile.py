# bench/locustfile.py
from locust import HttpUser, task, between
import uuid

class RAGUser(HttpUser):
    # 放慢一點，避免瞬間突刺
    wait_time = between(0.5, 1.5)

    def on_start(self):
        self.user_id = str(uuid.uuid4())
        self.payload = {
            "query": "系統架構有哪些元件？",
            "user": {"id": self.user_id, "role": "employee"}
        }

    @task
    def ask(self):
        r = self.client.post("/ask", json=self.payload, name="/ask")
        # 想觀察 429 時可記 log：
        # if r.status_code == 429:
        #     r.failure("rate limited")
