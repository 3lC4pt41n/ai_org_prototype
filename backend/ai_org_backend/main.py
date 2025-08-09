# ai_org_prototype.py – Autonomous-Agent SaaS · core API  (v1.9)
# ---------------------------------------------------------------
from __future__ import annotations

import os
from typing import Dict
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from sqlmodel import Session, select
from ai_org_backend.tasks.celery_app import celery
from fastapi import FastAPI, Depends
# Expose Repo here so existing imports keep working:
from .repo import Repo  # noqa: F401
from fastapi.middleware.cors import CORSMiddleware
from ai_org_backend.api.templates import router as tmpl_router
from ai_org_backend.api.agents import router as agent_router
from ai_org_backend.api.pipeline import router as pipeline_router
from ai_org_backend.api.auth import router as auth_router
from ai_org_backend.api.settings import router as settings_router
from ai_org_backend.api.root import router as root_router
from ai_org_backend.api.dependencies import get_current_tenant
from ai_org_backend.db import engine
# storage helpers are used by individual agent modules
from ai_org_backend.models import Task, Tenant
from prometheus_client import Counter, Histogram, Gauge, make_asgi_app
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
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
# Price per 1k tokens (USD)
TOKEN_PRICE_PER_1000 = float(os.getenv("TOKEN_PRICE_PER_1000", "0.0005"))

pool    = redis.from_url(REDIS_URL, decode_responses=True)
driver  = GraphDatabase.driver(NEO4J_URL, auth=(NEO4J_USER, NEO4J_PASS))

# ──────────────── Metrics Prometheus ──────────────────────────
if os.getenv("DISABLE_METRICS") != "1":
    TASK_LAT = Histogram("ai_task_latency_sec", "Task latency", ["role"])
    TASK_CNT = Counter("ai_tasks_total", "Tasks done", ["role", "status"])
    BUDGET_GA = Gauge("ai_budget_left_usd", "Budget left", ["tenant"])
else:  # create unregistered dummies
    TASK_LAT = Histogram(
        "ai_task_latency_sec", "Task latency", ["role"], registry=None
    )
    TASK_CNT = Counter(
        "ai_tasks_total", "Tasks done", ["role", "status"], registry=None
    )
    BUDGET_GA = Gauge(
        "ai_budget_left_usd", "Budget left", ["tenant"], registry=None
    )

# ──────────────── SQLModel tables ─────────────────────────────


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
from ai_org_backend.agents import repo_composer  # ensure repo_composer agent is loaded  # noqa: E402


# ──────────────── Agent tasks (imported) ─────────────
from ai_org_backend.agents.agent_dev import agent_dev  # noqa: E402
from ai_org_backend.agents.agent_ux_ui import agent_ux_ui  # noqa: E402
from ai_org_backend.agents.agent_qa import agent_qa  # noqa: E402


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
    yield

app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_methods=["*"],
    allow_headers=["*"]
)
app.include_router(auth_router)
app.include_router(tmpl_router)
app.include_router(agent_router)
app.include_router(pipeline_router)
app.include_router(settings_router)
app.include_router(root_router)

if os.getenv("DISABLE_METRICS") != "1":
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)


# CRUD endpoints (minimal)
@app.post("/task")
async def create_task(d: Dict, current_tenant: Tenant = Depends(get_current_tenant)):
    t = Repo(current_tenant.id).add_task(
        purpose_id=d.get("purpose_id"),
        description=d.get("description", "blank"),
        business_value=d.get("business_value", 1),
        tokens_plan=d.get("tokens_plan", 0),
        purpose_relevance=d.get("purpose_relevance", 0),
    )
    return t.model_dump()

@app.get("/backlog")
async def backlog(current_tenant: Tenant = Depends(get_current_tenant)):
    with Session(engine) as s:
        rows = s.exec(
            select(Task).where(Task.tenant_id == current_tenant.id, Task.status == "todo")
        ).all()
    return [r.model_dump() for r in rows]


# run dev server
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
