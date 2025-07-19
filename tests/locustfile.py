# tests/locustfile.py
"""
50-VU Smoke-Test – feuert POST /task + GET /backlog
  locust -f tests/locustfile.py --headless -u 50 -r 5 -t 30s --host http://localhost:8000
"""

from locust import HttpUser, task, between
import json, random, uuid

class AIOrgDemo(HttpUser):
    wait_time = between(0.1, 0.5)  # ~ 2–10 RPS pro User

    @task(3)
    def create_task(self):
        payload = {
            "description": f"demo-{uuid.uuid4().hex[:6]}",
            "value": random.randint(5, 50)
        }
        self.client.post("/task",
                         data=json.dumps(payload),
                         headers={"Content-Type": "application/json"})

    @task(1)
    def read_backlog(self):
        self.client.get("/backlog", name="/backlog")

    @task(1)
    def root_status(self):
        self.client.get("/", name="/")

    # optional basic auth for reverse-proxy demo
    # def on_start(self):
    #     self.client.auth = ("user", "pass")
