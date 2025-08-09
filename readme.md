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

## 🚀 1 | Quick Start (Local Dev / Docker)


```bash
# Clone repository
git clone https://github.com/3lC4pt41n/ai_org_prototype.git
cd ai_org_prototype

# Python ≥ 3.11
python -m venv .venv && source .venv/bin/activate  # Win: .venv\Scripts\activate
pip install -e backend[dev]

# Container-Infrastruktur (Backend, Orchestrator, Worker, Redis, Postgres, Neo4j)
docker compose -f ops/persistent.yml up -d
docker compose -f ops/monitoring.yml up -d  # prometheus + grafana

# DB migration & demo seed (nur erforderlich bei manuellem Start ohne Docker)
alembic -c backend/ai_org_backend/alembic.ini upgrade head
python scripts/seed_graph.py --tenant demo
```

2. Budget konfigurieren
Der Tokenpreis wird in `backend/ai_org_backend/settings.py` als `TOKEN_PRICE` definiert. Jeder
Mandant erhält beim ersten Start `settings.default_budget` USD (Redis Hash `budget:{tenant}`).

3. Celery-Worker starten *(bei Docker Compose bereits gestartet)*
```bash
celery -A ai_org_backend.tasks.celery_app \
       worker -Q demo:dev,demo:ux_ui,demo:qa,demo:telemetry \
       -l INFO -P solo
```

4. Orchestrator & Scheduler *(bei Docker Compose bereits gestartet)*
```bash
python -m ai_org_backend.orchestrator.scheduler
```

5. Frontend
```bash
cd frontend && pnpm i
pnpm --filter ./apps/web dev  # http://localhost:5173
```

### UI-Workflow
| Bereich | Beschreibung |
|---------|--------------|
| **Purpose Form** | Neues Projektziel eingeben → löst Architect-Seed aus |
| **Pipeline-Dashboard** | ReactFlow-Graph aller Tasks + Statusfarbe |
| **Artefacts** | Download-Liste aller vom System erzeugten Dateien |

### Budget-Gate
* Vor jedem Task-Publish greift ein **Celery-before_publish** Hook (siehe `backend/ai_org_backend/tasks/celery_app.py`).
* Wenn `budget_left < task.tokens_plan * TOKEN_PRICE`, wird der Task verworfen → Status `blocked` und Prometheus-Counter `ai_tasks_blocked` erhöht sich.

### Quality-Gate (Automatisierte Testprüfung)
* Nach jedem Dev-Task startet automatisch ein QA-Task, der generierte **Unit-Tests** ausführt.
* **Bestanden:** Alle Tests laufen erfolgreich → Artefakt `test_report.txt`, Task bleibt im Status `done`.
* **Fehlgeschlagen:** Bei Testfehlern oder wenn gar keine Tests vorhanden sind, wird der QA-Task mit Status `failed` markiert und ein Dev-Folgetask ("Fix failing tests" bzw. "Add tests") erzeugt.

### Smoke-Test
```bash
pytest -q backend/tests/test_smoke.py
```
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
POST    /api/register  Neuen Account anlegen (email + passwort)
POST    /api/login     JWT erhalten (Form: username, password)

> Alle geschützten Endpoints erwarten einen `Authorization: Bearer <token>` Header.


## 🔑 Authentication

POST /api/register – Neuen Account anlegen (email + passwort)

POST /api/login – JWT erhalten (Form: username, password)

Alle geschützten Endpoints erwarten einen `Authorization: Bearer <token>` Header.
