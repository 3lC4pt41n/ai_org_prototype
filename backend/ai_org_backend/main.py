# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Tim Mergenthaler
# ai_org_prototype.py – Autonomous-Agent SaaS · core API  (v2.0 – S6 hardened)
# ---------------------------------------------------------------
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Dict

from dotenv import load_dotenv
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from neo4j import GraphDatabase
from prometheus_client import make_asgi_app
from sqlmodel import SQLModel

import ai_org_backend.hooks.review_hook  # noqa: F401
import ai_org_backend.hooks.tests_hook  # noqa: F401
from ai_org_backend.api.agents import router as agent_router
from ai_org_backend.api.artifact_bridge import router as artifact_bridge_router
from ai_org_backend.api.auth import router as auth_router
from ai_org_backend.api.chat import router as chat_router
from ai_org_backend.api.chat import ws_router as chat_ws_router
from ai_org_backend.api.dependencies import get_current_tenant
from ai_org_backend.api.graphs import router as graphs_router
from ai_org_backend.api.health import router as health_router  # S6-05
from ai_org_backend.api.intent import router as intent_router
from ai_org_backend.api.pipeline import router as pipeline_router
from ai_org_backend.api.purposes import router as purposes_router
from ai_org_backend.api.reviews import router as reviews_router
from ai_org_backend.api.root import router as root_router
from ai_org_backend.api.settings import router as settings_router
from ai_org_backend.api.templates import router as tmpl_router
from ai_org_backend.db import engine
from ai_org_backend.metrics import BUDGET_GA, TASK_CNT, TASK_LAT
from ai_org_backend.middleware.exception_handler import install_exception_handlers  # S6-04
from ai_org_backend.middleware.input_sanitizer import InputSanitizerMiddleware  # S6-09
from ai_org_backend.middleware.metrics_middleware import MetricsMiddleware  # S6-07
from ai_org_backend.middleware.rate_limit import RateLimitMiddleware  # S6-01
from ai_org_backend.middleware.request_id import RequestIDMiddleware  # S6-03
from ai_org_backend.middleware.security_headers import SecurityHeadersMiddleware  # S6-02
from ai_org_backend.models import TaskOwner, Tenant
from ai_org_backend.services.graceful_shutdown import on_shutdown, on_startup  # S6-08
from ai_org_backend.services.repo import Repo, budget_left, debit  # noqa: F401
from ai_org_backend.settings import settings as app_settings  # S6 config
from ai_org_backend.tasks.celery_app import celery

load_dotenv()

# S6-06: Initialise structured logging before anything else runs
from ai_org_backend.services.structured_logging import setup_logging  # noqa: E402

setup_logging(level=app_settings.log_level, fmt=app_settings.log_format)

NEO4J_URL = os.getenv("NEO4J_URL", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASS = os.getenv("NEO4J_PASS")
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
# Price per 1k tokens (USD)
TOKEN_PRICE_PER_1000 = float(os.getenv("TOKEN_PRICE_PER_1000", "0.0005"))

driver = GraphDatabase.driver(NEO4J_URL, auth=(NEO4J_USER, NEO4J_PASS))

# ──────────────── Celery setup ───────────────────────────────
# (Celery app initialized in ai_org_backend.tasks.celery_app)

# import artefact helper
from ai_org_backend.agents import (  # ensure repo_composer agent is loaded  # noqa: E402
    repo_composer,
)

# ──────────────── Agent tasks (imported) ─────────────
from ai_org_backend.agents.agent_dev import agent_dev  # noqa: E402
from ai_org_backend.agents.agent_insight import agent_insight  # noqa: E402
from ai_org_backend.agents.agent_integration import agent_integration  # noqa: E402
from ai_org_backend.agents.agent_qa import agent_qa  # noqa: E402
from ai_org_backend.agents.agent_ux_ui import agent_ux_ui  # noqa: E402
from ai_org_backend.agents.product_owner import agent_po  # noqa: E402
from ai_org_backend.agents.reviewer import reviewer_task  # noqa: E402


@celery.task(name="agent.telemetry")
def agent_telemetry(tid: str, task_id: str):
    Repo(tid).update(
        task_id,
        status="done",
        owner=TaskOwner.TELEMETRY,
        notes="metrics emitted",
    )
    TASK_CNT.labels(tid, "telemetry", "done").inc()


AGENTS = {
    "dev": agent_dev,
    "ux_ui": agent_ux_ui,
    "qa": agent_qa,
    "telemetry": agent_telemetry,
    "insight": agent_insight,
    "integration": agent_integration,
    "repo": repo_composer.agent_repo,  # Register repo_composer agent  # type: ignore[has-type]
    "reviewer": reviewer_task,
    "po": agent_po,
}


# ──────────────── FastAPI + startup ─────────────────────────
import asyncio  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    # S6-08: startup hook
    on_startup()
    SQLModel.metadata.create_all(engine)

    # Start the orchestrator scheduler
    from ai_org_backend.orchestrator.scheduler import orchestrator

    asyncio.create_task(orchestrator())
    yield
    # S6-08: shutdown hook
    on_shutdown()


app = FastAPI(lifespan=lifespan)

# S6-04: Global exception handlers (must be installed before middleware)
install_exception_handlers(app)

# ── Middleware stack (order matters: outermost first) ──────────────────
# 1. Request ID — runs first so all downstream middleware/handlers see it
app.add_middleware(RequestIDMiddleware)
# 2. Security headers — runs on every response
app.add_middleware(SecurityHeadersMiddleware)
# 3. HTTP metrics — captures timing for all requests
app.add_middleware(MetricsMiddleware)
# 4. Rate limiting — reject abusive clients before reaching business logic
app.add_middleware(
    RateLimitMiddleware,
    requests_per_minute=app_settings.rate_limit_per_minute,
    burst=app_settings.rate_limit_burst,
)
# 5. Input sanitization — scan/reject dangerous payloads
app.add_middleware(
    InputSanitizerMiddleware,
    max_body_bytes=app_settings.max_request_body_bytes,
)
# 6. CORS — must be after security middleware so preflight gets headers
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=app_settings.cors_max_age,
)

# ── Routers ───────────────────────────────────────────────────────────
app.include_router(health_router)  # S6-05: health probes (no auth)
app.include_router(auth_router)
app.include_router(tmpl_router)
app.include_router(agent_router)
app.include_router(artifact_bridge_router)
app.include_router(intent_router)
app.include_router(graphs_router)
app.include_router(pipeline_router)
app.include_router(settings_router)
app.include_router(reviews_router)
app.include_router(root_router)
app.include_router(purposes_router)
app.include_router(chat_router)
app.include_router(chat_ws_router)


if os.getenv("DISABLE_METRICS") != "1":
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)


# CRUD endpoints (minimal)
@app.post("/task")
async def create_task(d: Dict, current_tenant: Tenant = Depends(get_current_tenant)):
    t = Repo(current_tenant.id).add_task(
        purpose_id=str(d.get("purpose_id", "")),
        description=d.get("description", "blank"),
        business_value=d.get("business_value", 1),
        tokens_plan=d.get("tokens_plan", 0),
        purpose_relevance=d.get("purpose_relevance", 0),
    )
    return t.model_dump()


# run dev server
if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
