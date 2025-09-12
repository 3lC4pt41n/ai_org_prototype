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
|**Monitoring‑Stack** | Prometheus :8000 (FastAPI) + Celery exporter; fertig provisionierte Grafana‑Dashboards |
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
pip install -e backend[dev]  # inkl. QA-Tools

# Container-Infrastruktur (Backend, Orchestrator, Worker, Redis, Postgres, Neo4j)
docker compose -f ops/persistent.yml up -d                      # API http://localhost:8000
docker compose -f ops/persistent.yml --profile ui up -d         # optionales Frontend http://localhost:5173
docker compose -f ops/monitoring.yml up -d                      # prometheus + grafana

# DB migration (nur erforderlich bei manuellem Start ohne Docker)
alembic -c backend/ai_org_backend/alembic.ini upgrade head
```

Backend API: http://localhost:8000
Docker-Frontend (`--profile ui`): http://localhost:5173

2. Budget konfigurieren
Der Tokenpreis wird in `backend/ai_org_backend/settings.py` als `TOKEN_PRICE` definiert. Jeder
Mandant erhält beim ersten Start `settings.default_budget` USD (Redis Hash `budget:{tenant}`).

3. Celery-Worker starten *(bei Docker Compose bereits gestartet)*
```bash
celery -A ai_org_backend.tasks.celery_app \
       worker -Q demo:dev,demo:ux_ui,demo:qa,demo:qa.review,demo:qa.refactor,demo:telemetry \
        -l INFO -P solo
```

> QA-Tasks laufen nur, wenn die benötigten Tools installiert sind (z.B. via `backend[dev]`); andernfalls wird ein Skip-Grund geloggt.

4. Orchestrator & Scheduler *(bei Docker Compose bereits gestartet)*
```bash
python -m ai_org_backend.orchestrator.scheduler
```

5. Frontend
```bash
cd frontend && pnpm i
pnpm --filter ./apps/web dev  # http://localhost:5173
# oder Docker: docker compose -f ops/persistent.yml --profile ui up -d
```

> ⚠️ Das Docker-Compose-Setup (Profil `ui`) mappt das Frontend auf Port 5173.
> Wenn du die Container startest, beende ggf. deinen lokalen `pnpm dev`
> oder ändere das Mapping (z.B. `8080:80`), um Port-Konflikte zu vermeiden.

### UI-Workflow
| Bereich | Beschreibung |
|---------|--------------|
| **Purpose Form** | Neues Projektziel eingeben → löst Architect-Seed aus |
| **Pipeline-Dashboard** | ReactFlow-Graph aller Tasks + Statusfarbe |
| **Artefacts** | Download-Liste aller vom System erzeugten Dateien |

### Budget-Gate
* Vor jedem Task-Publish greift ein **Celery-before_publish** Hook (siehe `backend/ai_org_backend/tasks/celery_app.py`).
* Wenn `budget_left < task.tokens_plan * TOKEN_PRICE`, wird der Task verworfen → Status `blocked` und Prometheus-Counter `ai_tasks_blocked` erhöht sich.

### Quality-Gate (Automatisierte Code- & Testprüfung)
* Wenn alle Entwicklungs-Tasks erledigt sind, führt ein **Code Review** Agent eine statische Analyse aus.
* Anschließend laufen Integration-, E2E-, Performance- und Security-Tests wie gewohnt.
* Nach erfolgreich bestandenen Tests schlägt ein **Refactor** Agent strukturelle Verbesserungen vor.
* **Fehlgeschlagen:** Bei Testfehlern oder wenn gar keine Tests vorhanden sind, wird der QA-Task mit Status `failed` markiert und ein Dev-Folgetask ("Fix failing tests" bzw. "Add tests") erzeugt.

### Smoke-Test
```bash
pytest -q backend/tests/test_smoke.py
```
### Integration-Test (Docker Compose)
```bash
docker compose --profile test up --build test-runner
```
> Baut Images und führt einen Playwright-Check gegen `http://frontend` aus. Bei Erfolg beendet sich der Container mit Code 0 und die Dienste fahren herunter.

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
scripts/                # helper scripts
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

PostgreSQL (in Dev und Prod) → Datenbank über Alembic‑Migrationen verwaltet.

**Datenmodelle & Beziehungen:** Das Backend nutzt SQLModel (SQLAlchemy) auf PostgreSQL mit den Haupt-Entitäten **Tenant**, **Purpose**, **Task**, **TaskDependency** und **Artifact** (zusätzlich existieren Feedback-Modelle). Ein *Tenant* (Mandant) kann mehrere **Purposes** besitzen (Projekte). Jede *Purpose* gehört zu genau einem Tenant und bildet einen Backlog (Sammlung von Tasks) für dieses Projekt. Die einzelnen *Tasks* sind über `tenant_id` und `purpose_id` einem Tenant bzw. Purpose zugeordnet. Tasks können Abhängigkeiten untereinander haben: die Tabelle **TaskDependency** verknüpft Tasks als gerichtete Kanten (von Vorgänger-Task zu Nachfolger-Task), um die Ablaufreihenfolge (z. B. „finish-to-start“) im Pipeline-Graph abzubilden. Jeder Task kann zudem mehrere **Artifacts** hervorbringen – Artefakte sind die von einem Task erzeugten Dateien oder Ergebnisse (z. B. Code oder Dokumentation), die mit `task_id` dem Task zugeordnet sind. Für Artefakte und Purposes existieren eigene Feedback-Tabellen: **ArtifactFeedback** speichert Review-Einträge (Versionen, Kommentare) zu einem Artefakt, während **Feedback** auf Purpose-Ebene genutzt wird, um Freigaben für zentrale Artefakte (etwa PRD oder Architektur-Blueprint) mit Versionsstand und Status festzuhalten.

🔌 4 | API‑Schnittstelle
In der FastAPI-Backend-API sind folgende zentrale Endpunkte definiert. *(Hinweis: Alle unten aufgeführten Routen unter `/api` erfordern einen gültigen Bearer-Token im `Authorization` Header, sofern nicht anders angegeben.)*

**Allgemein & Authentifizierung:**
- **GET /** – Öffentlicher Health-Check, liefert den API-Status und (für den Demo-Tenant) das verbleibende Budget (`budget_left`) sowie das Gesamtbudget (`budget_total`).
- **POST /api/register** – Neuen Tenant-Account registrieren (kein Auth-Token erforderlich). Erwartet JSON `{"email": ..., "password": ..., "name": ...}`; gibt bei Erfolg den neuen Tenant `id` und die `email` zurück.
- **POST /api/login** – Login und Token-Erhalt (kein Auth-Token erforderlich). Erwartet Form-Daten (`username`, `password` gemäß OAuth2 Standard); gibt ein JWT als `access_token` (Bearer) plus `token_type` zurück.

**Purpose-Verwaltung:**
- **GET /api/purposes** – Listet alle Purpose-Projekte des aktuellen Tenants als Array von Purpose-Objekten.
- **POST /api/purposes** – Erstellt eine neue Purpose (Projekt). Erwartet JSON `{"purpose": "<Name>", "mode": "manual"|...}`. Als Folge wird initial ein *Product Requirements Document* (PRD) via LLM-Agent erzeugt und als erster Task + Artefakt gespeichert. Response liefert u. a. `{"purpose_id": "...", "requirements": "<PRD-Inhalt>"}`.
- **GET /api/purposes/{purpose_id}/status** – Liefert Status-Infos zur angegebenen Purpose (z. B. `{"paused": false, "budget_left": 123.45, "budget_total": 200.0}`), inklusive Pipeline-Pause-Flag und aktuellem Budget.

**Backlog & Tasks:**
- **GET /api/backlog** – Gibt alle offenen Tasks (Status "todo") des Tenants zurück, optional gefiltert per `?purpose_id=<ID>` für einen Purpose. Response: Liste von Task-Objekten (mit Feldern wie `id`, `description`, `status`, `purpose_id` etc.).
- **POST /task** – Fügt einen neuen Task manuell hinzu. Erwartet JSON (z. B. `{"description": "...", "business_value": 5, ...}`); der Task wird dem Tenant und optional einem Purpose (via `purpose_id`) zugeordnet. Response enthält den erzeugten Task (inkl. generierter `id` und Default-Werten).

**Pipeline & Graph:**
- **GET /api/graph** – Liefert den vollständigen Aufgaben-Graphen des Tenants als JSON. Enthält `{"tasks": [...]}` (Liste aller Task-Objekte) und `{"dependencies": [...]}` (Kantenliste mit `from_id` → `to_id`).
- **GET /api/purposes/{purpose_id}/graph** – Wie `/api/graph`, aber gefiltert auf einen einzelnen Purpose. Gibt nur Tasks+Dependencies dieses Projekts zurück.
- **POST /api/pause** – Pausiert die Pipeline-Ausführung für den aktuellen Tenant. (Setzt ein Pause-Flag, so dass der Orchestrator keine neuen Tasks startet.) Response: `{"status": "paused"}`.
- **POST /api/resume** – Beendet einen gesetzten Pause-Zustand und setzt die automatische Ausführung fort. Response: `{"status": "resumed"}`.

**Artefakte & Ergebnisse:**
- **GET /api/artifacts** – Listet alle Artefakte des Tenants auf (optional filterbar mit `?purpose_id=<ID>`). Jedes Artefakt-Objekt enthält u. a. `id`, zugehörige `task_id`+`task_desc`, den Speicherpfad `repo_path`, den MIME-Typ `media_type`, Zeitstempel `created_at` und ein `released`-Flag. Zudem wird eine Download-URL (`/api/artifact/<id>`) angegeben.
- **GET /api/artifact/{artifact_id}** – Download eines Artefakts als Datei. (Gibt den Datei-Inhalt des angegebenen Artefakts zurück, z. B. Code oder Markdown.)
- **POST /api/artifacts/{artifact_id}/approve** – Markiert ein Artefakt als *freigegeben*. Dadurch wird ein ggf. gesetzter Pipeline-Pausezustand für die zugehörige Purpose aufgehoben, so dass der Orchestrator weiterarbeiten kann. Response: `{"status": "approved"}`.
- **GET /api/artifacts/{artifact_id}/feedback** – Holt alle Feedback-Einträge zu einem Artefakt (Liste mit History der Reviews). Jeder Eintrag enthält u. a. `author`, `content` (Text), `version` und `created_at`.
- **GET /api/project.zip** – Stellt alle Artefakte des Tenants in einem ZIP-Archiv zum Download bereit (kompletter Projekt-Output als ZIP).

**Einstellungen:**
- **GET /api/settings/research** – Liefert die aktuelle Einstellung, ob Agents Web-Recherchen durchführen dürfen (`{"allow_web_research": true|false}`).
- **POST /api/settings/research** – Setzt die *Web-Research*-Einstellung für den Tenant. Erwartet JSON `{"allow_web_research": true|false}`; Response spiegelt den neuen Wert wider.
📈 5 | Monitoring
Prometheus scraped Targets

FastAPI :8000 (uvicorn start)

Celery Worker :5555 (via env exporter)

Grafana Dashboards (dashboards/*.json)

admin_dashboard – Task‑Latency Histogram, Budget Gauge

ai_org_overview – Blocked‑Tasks, Critical‑Path‑Len

🧮 6 | LLM‑Token‑Budget
Flat price 0.0005 USD / 1 k Tokens (konfigurierbar in .env).

Redis‑Hash budget:{tenant} hält Rest‑Budget.

Celery‑Before‑Publish‑Hook bricht Task ab, wenn left < cost.

♻️ 7 | Orchestrator Flow
- **Initialisierung neuer Projekte:** Beim Anlegen einer neuen Purpose (Projekt) sorgt der Orchestrator für ein initiales Backlog. Dazu werden spezielle LLM-Agents aktiv – der *Product Owner* Agent generiert ein *Product Requirements Document* (Produktkonzept), anschließend erstellt der *Architect* einen Architektur-Blueprint und der *Planner* plant daraus initiale Tasks. Diese Tasks (inklusive z. B. "Initialize repository", "Product Requirements Document", "Architecture Blueprint") werden mit ihren Abhängigkeiten in der Datenbank angelegt. Falls beim Start des Systems ein aktiver Purpose noch keinen Backlog hat, führt `seed_if_empty` diesen Seed-Schritt automatisch aus.
- **Laufende Ablaufsteuerung:** Der Orchestrator läuft als Hintergrund-Scheduler, der kontinuierlich alle offenen Tasks überwacht und zum richtigen Zeitpunkt ausführt. Über Graph-Abfragen (Neo4j) ermittelt er alle bereitstehenden "todo"-Tasks ohne unerledigte Vorgänger. Für jeden solchen Task wird anhand der Beschreibung ein zuständiger Rollen-Agent bestimmt (z. B. *Dev*, *QA*, *UX/UI*), entweder per festen Schlüsselworten oder via LLM-Klassifizierung (`classify_role`). Anschließend setzt der Orchestrator den Task auf "doing" und gibt ihn an einen Celery-Worker der entsprechenden Agentenrolle zur Ausführung. Der Agent bearbeitet die Aufgabe (z. B. Code implementieren, Test durchführen) und erstellt dabei eventuell ein Artefakt.
- **Abhängigkeits-Graph:** Alle Tasks einer Purpose sind über **TaskDependency**-Kanten zu einem gerichteten azyklischen Graph verbunden. Der Orchestrator stellt sicher, dass kein Task ausgeführt wird, solange abhängige Vorgänger-Tasks noch nicht *done* sind. Über `/api/graph` bzw. `/api/purposes/{id}/graph` kann der aktuelle Task-Graph (Knoten: Tasks mit Status, Kanten: Abhängigkeiten) abgerufen werden.
- **Nutzer-Freigaben:** Bestimmte Schlüssel-Artefakte erfordern eine manuelle Abnahme, bevor es im Pipeline-Prozess weitergeht. Zum Beispiel pausiert nach Abschluss des PRD-Tasks die Planung, bis das erzeugte PRD-Artefakt vom Nutzer geprüft und via `POST /api/artifacts/{artifact_id}/approve` explizit freigegeben wurde. Ist dies geschehen, startet der Orchestrator die nächste Phase: der *Architect* erstellt den *Architecture Blueprint* und der *Planner* erzeugt daraufhin die Implementierungs-Tasks. Ähnlich muss ein später erstellter *Architecture & Domain Review*-Task vom Nutzer über `/reviews/{task_id}/approve` genehmigt werden, bevor die finalen Schritte erfolgen. Der Orchestrator überwacht solche Freigaben (Flags wie `Artifact.released` bzw. Feedback-Einträge) und setzt die Pipeline fort, sobald die Zustimmung vorliegt.
- **Fehlerbehandlung & Budget:** Fehlgeschlagene Tasks werden vom Orchestrator automatisch neu versucht (mit begrenzter Anzahl an Retries). Vor dem Start eines Tasks prüft das System außerdem, ob das geschätzte Token-Kontingent (`tokens_plan`) im verbleibenden Budget liegt – ist das Budget zu gering, wird der Task übersprungen (Status wechselt auf "budget_exceeded"). Über `POST /api/pause` bzw. `/api/resume` kann ein Administrator die Pipeline des Tenants manuell anhalten oder weiterlaufen lassen. Zudem protokolliert der Orchestrator laufend Metriken (z. B. Anzahl blockierter Tasks, kritische Pfadlänge) nach Prometheus, um den Fortschritt und Engpässe sichtbar zu machen.
💻 8 | Frontend (React)
AdminDashboard.tsx – Prometheus‑Gauge (via /metrics), Backlog‑Table.

TaskGraph.tsx – React‑Flow DAG; Bubble‑Size = business_value, Farbe = Status.

Vite Proxy → /api/* auf :8000, Tailwind 3.x, PNPM Workspaces.

🛣 9 | Roadmap (Q3 → Q4 2025)
 Sprint          Feature 
S‑1     Deep‑Research‑Agent (SERP + PDF Summariser)
S‑2     Self‑Improve‑Agent (PR‑Generator + CI Gate)
S‑3     Slack/Discord Notification Hooks
S‑4     JWT‑Auth + Stripe Billing (Multi‑Tenant)
S‑5     Autoscaling Celery on K8s + Helm Charts
