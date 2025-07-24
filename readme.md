# AI‑Org Prototype **2.0**  
Autonomous‑Agent SaaS • Neo4j‑driven • Multi‑Tenant • Token‑Aware • Prometheus‑Instrumented

> End‑to‑End Skeleton, das ganze Software‑Projekte mittels LLM‑Agenten plant, baut, testet und ausliefert.  
> **Stack:** Python 3.11 · FastAPI · Celery · SQLModel/Alembic · Neo4j 5 · Redis 7 · Prometheus/Grafana · React 18 / Vite / Tailwind · Node 20

---

## ✨ Hauptfeatures

| Modul | Kurzbeschreibung |
|-------|------------------|
|**Graph Orchestrator 2.0** | Neo4j als Source of Truth, LLM‑basiertes Role‑Routing, Prom‑Metriken (blocked tasks, critical path, alert‑counter) |
|**Erweitertes Task‑Modell** | Business‑Wert, Token KPI (Plan + Actual), Purpose‑Relevance, Multi‑Tenant FK |
|**Budget‑Gate** | Redis‑Hash `budget:{tenant}` + Celery‑Hook (Abbruch wenn Budget < 1 USD) |
|**Monitoring‑Stack** | Prometheus :9102 (FastAPI) + Celery exporter; fertig provisionierte Grafana‑Dashboards |
|**React Admin‑Dashboard** | Budget‑Gauge, Backlog‑Table, React‑Flow‑Graph (Bubble‑Size = Value, Color = Status) |
|**Monorepo** | Frontend‑Workspaces (`apps/web`, `packages/ui`, `packages/api-client`), Backend `ai_org_backend` |

---

## 🚀 1 | Quick Start (Local Dev)

```bash
# Klonen
git clone https://github.com/your‑org/ai_org_prototype.git
cd ai_org_prototype

# Python venv
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e backend[dev]

# Container‑Infra (Redis, Postgres optional, Neo4j, Prom/Grafana)
docker compose -f ops/persistent.yml up -d    # redis + postgres
docker compose -f ops/graph.yml      up -d    # neo4j  :7687 /7474
docker compose -f ops/monitoring.yml up -d    # prometheus :9090 + grafana :3000

# DB‑Migration + Demo‑Seed
alembic -c backend/ai_org_backend/alembic.ini upgrade head
python scripts/seed_graph.py --tenant demo
Dienste starten (dev)
bash
Kopieren
# 1 Celery‑Workers (Queues: demo:dev, demo:ux_ui …)
celery -A ai_org_backend.tasks.celery_app worker \
       -Q demo:dev,demo:ux_ui,demo:qa,demo:telemetry -l INFO -P solo

# 2 FastAPI‑Backend (REST + Prom + OpenAPI)
uvicorn ai_org_backend.main:app --reload  # http://localhost:8000

# 3 Orchestrator‑Loop
python -m ai_org_backend.orchestrator.scheduler   # zeigt Budget/Blocked/Path

# 4 React‑Frontend
pnpm --filter ./frontend/apps/web install
pnpm --filter ./frontend/apps/web dev              # http://localhost:5173
Service	URL/Port	Default‑Creds
FastAPI API	http://localhost:8000	–
Redis	localhost:6379	ai_redis_pw
Neo4j Browser	http://localhost:7474	neo4j / s3cr3tP@ss
Grafana	http://localhost:3000	admin / prom-graph

🗂 2 | Code‑Struktur (Backend + Frontend)
text
Kopieren
backend/
└─ ai_org_backend/
   ├─ config.py         # ENV via Pydantic‑Settings
   ├─ db.py             # SQLModel Engine + Session
   ├─ main.py           # FastAPI entry
   ├─ models/           # Tenant, Task, Artifact
   ├─ services/         # graph_service, storage, billing
   ├─ tasks/            # celery_app, llm_tasks (dev / ux_ui / qa / telemetry)
   ├─ orchestrator/     # core, graph_orchestrator, executor, router, inspector, scheduler
   ├─ api/              # routers + dependencies
   └─ alembic/          # migrations/
frontend/
└─ apps/web/            # React 18 + Vite
   └─ src/pages/        # AdminDashboard.tsx, TaskGraph.tsx …
frontend/packages/
   ├─ ui/               # Shared UI (Button, Card …) + Storybook
   └─ api-client/       # OpenAPI‑Hooks (axios)
ops/                    # docker‑compose + Helm blueprints
prompts/                # Jinja2 Agent-Prompts
scripts/                # seed_graph.py etc.
📊 3 | Erweitertes Task‑Schema
Feld	Typ	Beschreibung
id	str PK	8‑char UID
tenant_id	str FK	Mandanten‑Isolation
description	text	Aufgaben­text
status	enum	todo / doing / done / failed
owner	str	Agent / Person
business_value	float	€‑ oder Punkte‑Wert
tokens_plan	float	geplantes Budget (1k Tokens)
tokens_actual	float	real verbraucht
purpose_relevance	float	0‑1; wichtiger = größerer Bubble
depends_on	str FK	☺ DAG‑Kante
created_at	datetime	ISO‑UTC

SQLite für Dev, Postgres → Alembic‑Migrations.

🔌 4 | REST API (Auszug)
 Methode 	 Pfad 	 Beschreibung 
GET	/	Health + Budget Left
GET	/backlog	Liste aller todo‑Tasks (Tenant)
POST	/task	JSON {description, business_value} → Task anlegen
GET	/api/graph	Graph‑JSON (Nodes + Edges) für Frontend

📈 5 | Monitoring
Prometheus scraped Targets

FastAPI :9102 (uvicorn start)

Celery Worker :5555 (via env exporter)

Grafana Dashboards (dashboards/*.json)

admin_dashboard – Task‑Latency Histogram, Budget Gauge

ai_org_overview – Blocked‑Tasks, Critical‑Path‑Len

🧮 6 | LLM‑Token‑Budget
Flat price 0.0005 USD / 1 k Tokens (konfigurierbar in .env).

Redis‑Hash budget:{tenant} hält Rest‑Budget.

Celery‑Before‑Publish‑Hook bricht Task ab, wenn left < cost.

♻️ 7 | Orchestrator Flow
Seed‑Check → wenn Backlog leer → Architect/Planner Jinja‑Prompts → Neo4j Nodes

Role‑Classifier (router.py) → LLM oder Keyword‑Fallback

Dispatch → Celery Queue <tenant>:<role>

Agent‑Tasks erzeugen Artefakt + schreiben Tokens/Status zurück

Inspector Loop sammelt Blocked‑Count, Critical‑Path‑Len → Prometheus

Budget‑Debit nach jedem Task (tokens_actual * price)

💻 8 | Frontend (React)
AdminDashboard.tsx – Prometheus‑Gauge (via /metrics), Backlog‑Table.

TaskGraph.tsx – React‑Flow DAG; Bubble‑Size = business_value, Farbe = Status.

Vite Proxy → /api/* auf :8000, Tailwind 3.x, PNPM Workspaces.

🛣 9 | Roadmap (Q3 → Q4 2025)
 Sprint 	 Feature 
S‑1	Deep‑Research‑Agent (SERP + PDF summariser)
S‑2	Self‑Improve‑Agent (PR‑Generator + CI Gate)
S‑3	Slack / Discord Notification Hooks
S‑4	JWT‑Auth + Stripe‑Top‑Up (Multi‑Tenant Billing)
S‑5	Autoscaling Celery on K8s + Helm Charts