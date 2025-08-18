# AI_org – Lokales Setup (Docker Compose)
**Version:** Community Edition · **Modus:** Lokale Entwicklung & Demo

> Dieses README fasst den *AI_org Local Setup Guide (Docker Compose)* als kompaktes, praxisnahes How‑to zusammen.
> Ziel: In wenigen Minuten lokal lauffähig – mit Backend (FastAPI), Agenten (Celery), Redis, Neo4j, Qdrant sowie optionalem UI.

---

## ⚡ TL;DR (Schnellstart)

```bash
# 1) Repository clonen
git clone https://github.com/3lC4pt41n/ai_org_prototype.git
cd ai_org_prototype

# 2) Umgebungsvariablen vorbereiten
cp .env.example .env
# WICHTIG: In .env u. a. OPENAI_API_KEY, QDRANT_URL, REDIS_URL, NEO4J_URL prüfen/anpassen

# 3) Docker Compose starten (persistentes Setup)
docker compose -f ops/persistent.yml up -d

# 4) Status checken
docker compose ps
# Backend:   http://localhost:9102
# Frontend:  http://localhost:5173  (optional, falls UI-Container aktiv)
# Neo4j:     http://localhost:7474 (Browser) / bolt://localhost:7687
# Qdrant:    http://localhost:6333 (REST API)
# Grafana:   http://localhost:3000 (falls aktiviert)
```

---

## Inhaltsverzeichnis
- [Voraussetzungen](#voraussetzungen)
- [Überblick: Architektur & Dienste](#überblick-architektur--dienste)
- [Umgebungsvariablen (.env)](#umgebungsvariablen-env)
- [Starten mit Docker Compose](#starten-mit-docker-compose)
- [Lokale Entwicklung (ohne Container)](#lokale-entwicklung-ohne-container)
- [UI/Frontend (optional, pnpm)](#uifrontend-optional-pnpm)
- [Daten & Volumes](#daten--volumes)
- [Troubleshooting](#troubleshooting)
- [Nützliche Befehle](#nützliche-befehle)

---

## Voraussetzungen

- **Docker** & **Docker Compose** (aktuelle Versionen)
- **Git** (zum Clonen)
- Optional für lokale Dev‑Runs (ohne Container):
  - **Python 3.10+**, **pip** und ggf. **uvicorn**, **celery**
  - **Node 20+** und **pnpm** (für UI‑Entwicklung)

> **Hinweis:** Der Standard‑Stack nutzt Container für Backend, Celery‑Worker, Redis, Neo4j, Qdrant sowie (optional) Prometheus/Grafana und die UI.

---

## Überblick: Architektur & Dienste

- **Backend API (FastAPI)** – läuft typischerweise auf **http://localhost:9102**.
  Stellt REST‑Endpunkte bereit (z. B. Task anlegen, Backlog einsehen) und orchestriert Agenten.
- **Celery Worker / Beat** – führt Agenten‑Tasks asynchron aus.
- **Redis 7** – Queue & Cache.
- **Neo4j** – Graphdatenbank für Task↔Artifact‑Beziehungen.
  Browser: **http://localhost:7474**, Bolt: **bolt://localhost:7687**.
- **Qdrant** – Vektor‑Datenbank für semantische Suche (Langzeitgedächtnis).
  REST: **http://localhost:6333**.
- **Prometheus / Grafana** (optional) – Monitoring (z. B. `/metrics` vom Backend).
- **Frontend (Vite/React/Tailwind)** (optional) – typischer Dev‑Port **5173**.

> Die Container und Ports variieren je nach Compose‑Profil; das persistente Setup in `ops/persistent.yml` richtet stabile Volumes und Ports ein.

---

## Umgebungsvariablen (.env)

Erstelle eine `.env` (z. B. aus `.env.example`) und pflege u. a.:

```dotenv
# Backend & Orchestrierung
DATABASE_URL=postgresql+psycopg2://postgres:ai@localhost:5432/ai_org  # PostgreSQL-Verbindungs-URL für die Datenbank
REDIS_PASSWORD=ai_redis_pw
REDIS_URL=redis://:${REDIS_PASSWORD}@localhost:6379/0
NEO4J_URL=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASS=s3cr3tP@ss

# Vektor-Store
QDRANT_URL=http://localhost:6333

# LLMs / Embeddings
OPENAI_API_KEY=sk-...                    # falls OpenAI genutzt wird
TOKEN_PRICE_PER_1000=0.0005              # interne Kalkulation

# Sonstiges
DEFAULT_BUDGET=20
DISABLE_METRICS=0
```

> **Tipp:** Für Postgres‑Betrieb die entsprechenden DSN/Secrets einsetzen und das Compose‑Profil aktivieren (siehe `ops/persistent.yml`).
> **Tipp:** Stelle sicher, dass die DB-Verbindung korrekt konfiguriert ist (Standard-Zugangsdaten siehe `ops/persistent.yml` bzw. `.env.example`). Bei abweichenden Credentials müssen `DATABASE_URL` bzw. `POSTGRES_*` Variablen angepasst werden.

---

## Starten mit Docker Compose

**Persistentes Setup (empfohlen für lokale Nutzung):**

```bash
docker compose -f ops/persistent.yml up -d
# Logs ansehen (alle Services)
docker compose -f ops/persistent.yml logs -f --tail=200
```

**Stoppen & Aufräumen:**

```bash
docker compose -f ops/persistent.yml down
# optional inkl. Volumes
docker compose -f ops/persistent.yml down -v
```

Nach dem Start erreichst du u. a.:

- **Backend:** http://localhost:9102  (Health/Metrics verfügbar)
- **UI (optional):** http://localhost:5173
- **Neo4j:** http://localhost:7474  (Login mit NEO4J_USER/NEO4J_PASS)
- **Qdrant:** http://localhost:6333

---

## Lokale Entwicklung (ohne Container)

> Für schnelles Iterieren lässt sich Backend & Worker auch direkt lokal starten. Redis/Neo4j/Qdrant können weiter im Container laufen.

**Backend (Uvicorn):**
```bash
# Ab Projektwurzel (mit aktiviertem venv)
pip install -e backend/.[dev]
uvicorn ai_org_backend.main:app --reload --port 9102
```

**Celery Worker:**
```bash
celery -A ai_org_backend.tasks.celery_app.celery worker --loglevel=INFO
# optional: Celery Beat falls periodische Aufgaben vorgesehen sind
```

Passe `.env` so an, dass die Endpunkte (REDIS_URL, NEO4J_URL, QDRANT_URL) zu deinen laufenden Containern zeigen.

---

## UI/Frontend (optional, pnpm)

Das UI basiert auf Vite/React/Tailwind. Für lokale Entwicklung:

```bash
# Im UI-Projektverzeichnis (z. B. apps/ui oder frontend)
pnpm install
pnpm dev
# -> verfügbar auf http://localhost:5173
```

> Falls dein CI „`npm ci`“ ausführt und kein `package-lock.json` existiert, stelle im CI auf **pnpm** um (oder erzeuge testweise ein Lockfile).

---

## Daten & Volumes

Das Compose‑Setup mountet u. a. folgende persistente Verzeichnisse/Volumes:

- `workspace/` – Ablage für generierte Artefakte (vom Backend verwaltet).
- `neo4j_data/` – Datenverzeichnis von Neo4j.
- `qdrant_storage/` – Persistenz der Vektordaten.
- ggf. `postgres_data/` – falls Postgres aktiviert ist.

> Das Backend commitet Artefakte zusätzlich in ein Git‑Repo im `workspace/`‑Baum und verknüpft sie im Neo4j‑Graphen.

---

## Troubleshooting

- **Backend nicht erreichbar / Health schlägt fehl**
  → Logs prüfen: `docker compose -f ops/persistent.yml logs -f backend`
  → `.env` prüfen (DB/Redis/Neo4j/Qdrant URLs & Credentials).

- **Celery verarbeitet keine Tasks**
  → Redis läuft? `docker compose ps`
  → Worker‑Logs ansehen: `docker compose -f ops/persistent.yml logs -f worker`

- **Neo4j Login fehlgeschlagen**
  → Nutzer/Passwort aus `.env` verwenden, ggf. Container einmal neu starten.

- **Qdrant liefert 404/Verbindungsfehler**
  → URL prüfen (`QDRANT_URL`). In Compose standardmäßig: `http://qdrant:6333` (im Container‑Netz) bzw. `http://localhost:6333` (Host).

- **UI zeigt keine Daten**
  → Backend läuft auf `http://localhost:9102`? CORS aktiviert? WebSocket‑Endpunkte erreichbar?

---

## Nützliche Befehle

```bash
# Dienste-Status
docker compose -f ops/persistent.yml ps

# Einzelne Service-Logs (Beispiel: backend)
docker compose -f ops/persistent.yml logs -f backend

# Compose neu bauen (z. B. nach Codeänderungen am Backend)
docker compose -f ops/persistent.yml build backend
docker compose -f ops/persistent.yml up -d backend
```

---

### Quellen
Dieses README ist eine kuratierte, deutschsprachige Zusammenfassung des Dokuments
**„AI_org Local Setup Guide (Docker Compose)“** (Stand: lokal mitgelieferte PDF).
