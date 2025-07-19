# AI‑Org Prototype 2.0

> **Autonomous‑Agent SaaS skeleton** – token‑aware, multi‑tenant, Prometheus‑instrumented.  Now with:
>
> - external `` (Neo4j‑driven, LLM‑routed)
> - extended **Task model** (business value & token KPIs)
> - Grafana/Prometheus, React admin dashboard & graph view
>
> Built & tested on Python 3.11 / Node 20 / Neo4j 5 / Redis 7.

---

## 1  Quick Start

```bash
# clone & enter
$ git clone https://github.com/your‑org/ai_org_prototype.git && cd ai_org_prototype

# Python venv
$ python -m venv venv && source venv/bin/activate       # Windows: venv\Scripts\activate
$ pip install -r requirements.txt

# Containers (Postgres optional ⇒ default SQLite)
$ docker compose -f ops/persistent.yml   up -d   # redis + postgres
$ docker compose -f ops/graph.yml        up -d   # neo4j
$ docker compose -f ops/monitoring.yml   up -d   # prometheus + grafana

# DB bootstrap (optional demo data)
$ python scripts/seed_graph.py --tenant demo
```

### Run services (dev mode)

```bash
# 1.  Celery workers (queues: dev, telemetry, ux_ui, qa)
$ celery -A ai_org_prototype.celery worker -Q demo:dev,demo:telemetry,demo:ux_ui,demo:qa -l INFO -P solo

# 2.  FastAPI backend (Graph, backlog, budget)
$ python ai_org_prototype.py --synthetic                # add --synthetic to stub LLM calls

# 3.  Orchestrator (LLM‑routed, insights)
$ python orchestrator.py                                # ⇠  shows blocked tasks / critical path

# 4.  React frontend (admin dashboard + graph)
$ cd project && npm i && npm run dev                    # http://localhost:5173
```

Default credentials / ports

| Service | URL / Port  | creds                               |
| ------- | ----------- | ----------------------------------- |
| FastAPI | :8000       | –                                   |
| Redis   | :6379       | `ai_redis_pw`                       |
| Neo4j   | :7687 /7474 | `neo4j / s3cr3tP@ss`                |
| Grafana | :3000       | `admin / prom-graph` (set on first) |

---

## 2  Code Structure

```
ai_org_prototype/
├── ai_org_prototype.py   ← API, DB models, Celery app, token‑gate
├── orchestrator.py       ← Neo4j loop, LLM routing, monitoring
├── prompts/              ← *.j2 agent prompts (architect, planner…)
├── project/              ← Vite + React dashboard / graph view
├── scripts/seed_graph.py ← one‑shot SQL→Neo4j migrator
└── ops/                  ← docker‑compose stacks
```

### Extended `TaskDB` schema

| column             | type   | notes                             |
| ------------------ | ------ | --------------------------------- |
| id                 | str PK | 8‑char UID                        |
| tenant\_id         | str FK | multi‑tenant segregation          |
| description        | text   | human‑readable                    |
| status             | enum   | `todo / doing / done / failed`    |
| owner              | str    | agent / human                     |
| est\_value         | float  | **business value (€ / points)**   |
| tokens\_plan       | float  | budget estimate (1k‑token blocks) |
| tokens\_actual     | float  | real usage (updated by agents)    |
| purpose\_relevance | float  | 0‑1 scoring vs. overall purpose   |
| depends\_on        | str FK | edge → another task               |
| created\_at        | dt     |                                   |

> **Migration**: SQLite auto‑altered via SQLModel; for Postgres run Alembic.

---

## 3  API

| Method | Path         | Purpose                             |
| ------ | ------------ | ----------------------------------- |
| GET    | `/`          | health + budget\_left               |
| GET    | `/backlog`   | list *todo* tasks for tenant        |
| POST   | `/task`      | `{description, value}` → new Task   |
| GET    | `/api/graph` | returns **nodes+edges** JSON for FE |

### `/api/graph` response

```json
{
  "nodes": [
    {"id":"t1","label":"Init repo","status":"done","business_value":1.0,
     "tokens_plan":0.2,"tokens_actual":0.18,"purpose_relevance":0.9,
     "depends_on":null}
  ],
  "edges": [
    {"id":"t1->t2","source":"t1","target":"t2"}
  ]
}
```

---

## 4  Prometheus / Grafana

- Prom targets auto‑scraped on `:9102` (FastAPI) + Celery workers (via env)
- Dashboards: `dashboards/` folder auto‑provisioned → task latency, budget gauge, blocked‑task alerts.

---

## 5  LLM token‑budget Gate

- Flat price `0.0005 USD / 1k tokens` (configurable).
- Budget per tenant in Redis hash `budget:{tenant}`; Prom gauge `ai_tenant_budget`.
- **Before‑publish** Celery hook aborts tasks if budget exhausted.

---

## 6  Orchestrator 2.0

- **Neo4j** as single source of truth for task graph.
- Classifies role via OpenAI (`gpt‑3.5‑turbo`) or keyword fallback.
- Emits Prom metrics: blocked count, critical path length, alert counter.

---

## 7  Frontend

- **React + Vite** (Tailwind 3.x).
- `AdminDashboard.jsx` – budget gauge + backlog.
- `TaskGraph.jsx` – React‑Flow visualization (bubble size by business value; color by status).

---

## 8  Roadmap

1. **Deep‑Research agent**  (LLM w/ serpapi).
2. **Self‑Improve agent**  (PR + CI checks against repo).
3. **Slack / Discord hooks** for human‑in‑the‑loop.
4. Multi‑tenant auth (JWT) & Stripe top‑up.
5. Autoscaling Celery on Kubernetes.

---

## 9  License

MIT –  do whatever, no warranty.  Flame‑free zone.

