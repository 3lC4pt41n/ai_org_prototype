# ai_org_prototype.py – Autonomous-Agent SaaS · core API  (v1.9)
# ---------------------------------------------------------------
from __future__ import annotations

import os
from typing import Dict
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from sqlmodel import Session, select
from ai_org_backend.tasks.celery_app import celery
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from ai_org_backend.api.templates import router as tmpl_router
from ai_org_backend.api.agents import router as agent_router
from ai_org_backend.db import engine
from ai_org_backend.services.storage import register_artefact
from ai_org_backend.models import Task
from ai_org_backend.models.task import TaskStatus
from prometheus_client import Counter, Histogram, Gauge, start_http_server
from neo4j import GraphDatabase
import redis

# ──────────────── ENV / constants ─────────────────────────────
load_dotenv()

DB_URL        = os.getenv("DATABASE_URL", "sqlite:///ai_org.db")
REDIS_URL     = os.getenv("REDIS_URL", "redis://:ai_redis_pw@localhost:6379/0")
NEO4J_URL     = os.getenv("NEO4J_URL", "bolt://localhost:7687")
NEO4J_USER    = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS    = os.getenv("NEO4J_PASS", "s3cr3tP@ss")
DEFAULT_BUDGET= float(os.getenv("DEFAULT_BUDGET", 20))

pool    = redis.from_url(REDIS_URL, decode_responses=True)
driver  = GraphDatabase.driver(NEO4J_URL, auth=(NEO4J_USER, NEO4J_PASS))

# ──────────────── Metrics Prometheus ──────────────────────────
start_http_server(9102)
TASK_LAT   = Histogram("ai_task_latency_sec", "Task latency", ["role"])
TASK_CNT   = Counter  ("ai_tasks_total",      "Tasks done",   ["role", "status"])
BUDGET_GA  = Gauge     ("ai_budget_left_usd", "Budget left",  ["tenant"])

# ──────────────── SQLModel tables ─────────────────────────────


# ──────────────── Repo helper (mirrors Neo4j) ─────────────────
class Repo:
    def __init__(self, tenant: str):
        self.tid = tenant

    def add(
        self,
        description: str,
        business_value: float = 1.0,
        tokens_plan: int = 0,
        purpose_relevance: float = 0.0,
        purpose_id: str | None = None,
    ) -> Task:
        with Session(engine) as s:
            t = Task(
                tenant_id=self.tid,
                purpose_id=purpose_id,
                description=description,
                business_value=business_value,
                tokens_plan=tokens_plan,
                purpose_relevance=purpose_relevance,
            )
            s.add(t)
            s.commit()
            s.refresh(t)

        with driver.session() as g:
            g.run(
                """MERGE (t:Task {id:$id})
                   SET t.desc=$d, t.status='todo'""",
                id=t.id,
                d=description,
            )
        return t

    def update(self, task_id: str, **kw):
        with Session(engine) as s:
            task = s.get(Task, task_id)
            for k, v in kw.items():
                if k == "status" and isinstance(v, str):
                    setattr(task, k, TaskStatus(v))
                else:
                    setattr(task, k, v)
            s.commit()
        if "status" in kw:
            with driver.session() as g:
                g.run(
                    "MATCH (t:Task {id:$id}) SET t.status=$st",
                    id=task_id,
                    st=str(kw["status"]),
                )

# ──────────────── Budget utils ───────────────────────────────
def budget_left(tenant: str = "demo") -> float:
    return float(pool.hget("budget", tenant) or DEFAULT_BUDGET)

def debit(tenant: str, amount: float):
    left = max(budget_left(tenant) - amount, 0)
    pool.hset("budget", tenant, left)
    BUDGET_GA.labels(tenant).set(left)

# ──────────────── Celery setup ───────────────────────────────
# (Celery app initialized in ai_org_backend.tasks.celery_app)

# import artefact helper
from ai_org_backend.agents import repo_composer  # ensure repo_composer agent is loaded


# ──────────────── Agent stubs (patched) ──────────────────────
@celery.task(name="agent.dev")
def agent_dev(tid: str, task_id: str):
    with TASK_LAT.labels("dev").time():
        code = f"# Auto-generated stub for {task_id}\n\ndef foo():\n    return 42\n"
        register_artefact(task_id, code.encode(), filename=f"{task_id}.py")
        Repo(tid).update(task_id, status="done", owner="Dev", notes="stub code")
    TASK_CNT.labels("dev", "done").inc()


@celery.task(name="agent.ux_ui")
def agent_ux_ui(tid: str, task_id: str):
    with TASK_LAT.labels("ux_ui").time():
        html = f"<!-- mock wireframe for {task_id} -->\n<div class='p-4'>TODO UI</div>"
        register_artefact(task_id, html.encode(), filename=f"{task_id}.html")
        Repo(tid).update(task_id, status="done", owner="UX/UI", notes="wireframe")
    TASK_CNT.labels("ux_ui", "done").inc()


@celery.task(name="agent.qa")
def agent_qa(tid: str, task_id: str):
    with TASK_LAT.labels("qa").time():
        report = f"QA report for {task_id}: ✅ looks good"
        register_artefact(task_id, report.encode(), filename=f"{task_id}_qa.txt")
        Repo(tid).update(task_id, status="done", owner="QA", notes="qa pass")
    TASK_CNT.labels("qa", "done").inc()


@celery.task(name="agent.telemetry")
def agent_telemetry(tid: str, task_id: str):
    Repo(tid).update(task_id, status="done", owner="Telemetry", notes="metrics emitted")
    TASK_CNT.labels("telemetry", "done").inc()


AGENTS = {
    "dev": agent_dev,
    "ux_ui": agent_ux_ui,
    "qa": agent_qa,
    "telemetry": agent_telemetry,
    "repo": repo_composer.agent_repo,   # Register new repo_composer agent
}

# ──────────────── FastAPI + startup ─────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    Repo("demo").add("bootstrap metrics")
    yield

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(tmpl_router)
app.include_router(agent_router)


# CRUD endpoints (minimal)
@app.post("/task")
async def create_task(d: Dict):
    t = Repo("demo").add(
        description=d.get("description", "blank"),
        business_value=d.get("business_value", 1),
        tokens_plan=d.get("tokens_plan", 0),
        purpose_relevance=d.get("purpose_relevance", 0),
    )
    return t.model_dump()

@app.get("/backlog")
async def backlog():
    with Session(engine) as s:
        rows = s.exec(
            select(Task).where(Task.tenant_id == "demo", Task.status == TaskStatus.TODO)
        ).all()
    return [r.model_dump() for r in rows]

@app.get("/")
async def root():
    return {"status": "alive", "budget_left": budget_left()}

# run dev server
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
