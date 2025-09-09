# ai_org_prototype.py – Autonomous-Agent SaaS · core API  (v1.9)
# ---------------------------------------------------------------
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Dict

from dotenv import load_dotenv
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from neo4j import GraphDatabase
from prometheus_client import Counter, Gauge, Histogram, make_asgi_app
from sqlmodel import SQLModel

import ai_org_backend.hooks.review_hook  # noqa: F401
import ai_org_backend.hooks.tests_hook  # noqa: F401
from ai_org_backend.api.agents import router as agent_router
from ai_org_backend.api.auth import router as auth_router
from ai_org_backend.api.chat import router as chat_router
from ai_org_backend.api.chat import ws_router as chat_ws_router
from ai_org_backend.api.dependencies import get_current_tenant
from ai_org_backend.api.pipeline import router as pipeline_router
from ai_org_backend.api.purposes import router as purposes_router
from ai_org_backend.api.reviews import router as reviews_router
from ai_org_backend.api.root import router as root_router
from ai_org_backend.api.settings import router as settings_router
from ai_org_backend.api.templates import router as tmpl_router
from ai_org_backend.db import engine
from ai_org_backend.models import Tenant

# ──────────────── ENV / constants ─────────────────────────────
from ai_org_backend.redis_client import DEFAULT_BUDGET, pool
from ai_org_backend.tasks.celery_app import celery

# Expose Repo here so existing imports keep working:
from .repo import Repo  # noqa: F401

load_dotenv()
NEO4J_URL = os.getenv("NEO4J_URL", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASS = os.getenv("NEO4J_PASS")
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
# Price per 1k tokens (USD)
TOKEN_PRICE_PER_1000 = float(os.getenv("TOKEN_PRICE_PER_1000", "0.0005"))

driver = GraphDatabase.driver(NEO4J_URL, auth=(NEO4J_USER, NEO4J_PASS))

# ──────────────── Metrics Prometheus ──────────────────────────
if os.getenv("DISABLE_METRICS") != "1":
    TASK_LAT = Histogram("ai_task_latency_sec", "Task latency", ["role", "tenant"])
    TASK_CNT = Counter("ai_tasks_total", "Tasks done", ["tenant", "role", "status"])
    BUDGET_GA = Gauge("ai_budget_left_usd", "Budget left", ["tenant"])
else:  # create unregistered dummies
    TASK_LAT = Histogram("ai_task_latency_sec", "Task latency", ["role", "tenant"], registry=None)
    TASK_CNT = Counter("ai_tasks_total", "Tasks done", ["tenant", "role", "status"], registry=None)
    BUDGET_GA = Gauge("ai_budget_left_usd", "Budget left", ["tenant"], registry=None)

# ──────────────── SQLModel tables ─────────────────────────────


# ──────────────── Budget utils ───────────────────────────────
def budget_left(tenant: str = "demo", purpose: str | None = None) -> float:
    if purpose:
        # Return budget left for a specific purpose
        return float(pool.get(f"budget:{tenant}:{purpose}") or DEFAULT_BUDGET)
    # Sum budgets of all purposes for this tenant
    total = 0.0
    for key in pool.keys(f"budget:{tenant}:*"):
        total += float(pool.get(key) or 0)
    return total


def debit(tenant: str, amount: float, purpose: str | None = None):
    if purpose:
        current = float(pool.get(f"budget:{tenant}:{purpose}") or DEFAULT_BUDGET)
        left = max(current - amount, 0)
        pool.set(f"budget:{tenant}:{purpose}", left)
    else:
        # No purpose specified: do not alter any budget, just get total
        left = budget_left(tenant, None)
    BUDGET_GA.labels(tenant).set(left)


# ──────────────── Celery setup ───────────────────────────────
# (Celery app initialized in ai_org_backend.tasks.celery_app)

# import artefact helper
from ai_org_backend.agents import (  # ensure repo_composer agent is loaded  # noqa: E402
    repo_composer,
)

# ──────────────── Agent tasks (imported) ─────────────
from ai_org_backend.agents.agent_dev import agent_dev  # noqa: E402
from ai_org_backend.agents.agent_qa import agent_qa  # noqa: E402
from ai_org_backend.agents.agent_ux_ui import agent_ux_ui  # noqa: E402


@celery.task(name="agent.telemetry")
def agent_telemetry(tid: str, task_id: str):
    Repo(tid).update(task_id, status="done", owner="Telemetry", notes="metrics emitted")
    TASK_CNT.labels(tid, "telemetry", "done").inc()


AGENTS = {
    "dev": agent_dev,
    "ux_ui": agent_ux_ui,
    "qa": agent_qa,
    "telemetry": agent_telemetry,
    "repo": repo_composer.agent_repo,  # Register new repo_composer agent
}


# ──────────────── FastAPI + startup ─────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=[FRONTEND_ORIGIN], allow_methods=["*"], allow_headers=["*"]
)
app.include_router(auth_router)
app.include_router(tmpl_router)
app.include_router(agent_router)
app.include_router(pipeline_router)
app.include_router(settings_router)
app.include_router(reviews_router)
app.include_router(root_router)
app.include_router(purposes_router)
app.include_router(chat_router)
app.include_router(chat_ws_router)


# Ensure chat-related tables exist
@app.on_event("startup")
async def init_db():
    SQLModel.metadata.create_all(engine)


# ─────────────── Scheduler automatisch starten ─────────────────────────
import asyncio  # noqa: E402


@app.on_event("startup")
async def start_scheduler():
    from ai_org_backend.orchestrator.scheduler import orchestrator

    asyncio.create_task(orchestrator())


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


# run dev server
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
