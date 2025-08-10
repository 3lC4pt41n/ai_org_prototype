# AI_org Testing Pipeline (Multi‑Stage)

This repo adds **four** automated testing stages:

1. **Integration Tests** (`agent.integration`) – generated from PRD + Blueprint; black‑box HTTP + optional UI smoke.  
2. **E2E & Acceptance Tests** (`agent.e2e`) – derived from PRD acceptance criteria, optional Playwright UI.  
3. **Performance Tests** (`agent.performance`) – short headless Locust run; checks p95 budget.  
4. **Security Scan** (`agent.security`) – Bandit (Python SAST) + pip‑audit (deps).

## How it triggers
The system hooks **Repo.update**. When a task flips to **done**:

- If **all non‑test tasks** in the purpose are done → **Integration Tests** task is created and executed.
- Once Integration is **done** → **E2E** task is created and executed.
- Once E2E is **done** → **Performance** and **Security** tasks are created and executed (in parallel).

Each task produces artifacts in `workspace/<tenant>/reports/...` and marks itself **done** or **failed**. On failures, the agent creates follow‑up **Fix** tasks automatically.

## URLs and thresholds
Configure via env:
- `API_BASE_URL` – e.g., `http://backend:8000`
- `UI_BASE_URL` – e.g., `http://frontend:3000`
- `PERF_HOST` (fallback: `API_BASE_URL`), `PERF_USERS`, `PERF_SPAWN`, `PERF_TIME`, `PERF_P95_BUDGET_MS`

## Degradation
If tools are missing (Playwright, Locust, Bandit, pip‑audit), agents **skip gracefully** and report why. Install via Docker build or local venv for full coverage.

## Running locally
Start your Celery worker as usual; agents run on the default queue:
```bash
celery -A ai_org_backend.tasks.celery_app worker -l info
```
Then develop as normal; once your feature tasks complete, the test stages chain will execute.

---

### Warum das „just works“

- **Kein Router-Gefrickel:** Wir patchen `Repo.update`, beobachten Statuswechsel und **schicken die passenden Celery‑Jobs** los.  
- **Tenant‑aware:** Alle Tasks/Artefakte hängen an `tenant_id`/`purpose_id`.  
- **Robust bei fehlenden Tools:** Playwright/Locust/Bandit/pip‑audit werden **nicht erzwungen** – Tests werden sauber übersprungen und dokumentiert.  
- **Artefakte überall:** Testdateien und Reports landen unter `workspace/<tenant>/tests/...` und `workspace/<tenant>/reports/...` (über `save_artefact`).  
- **Folge‑Tasks:** Bei Failures legt der Agent **Fix‑Tickets** an, mit kompakten Fehlerlogs in `notes`.  
- **Compose ready:** Ich habe die Python‑Deps in `backend/requirements.txt` ergänzt; du kannst deinen Worker‑Container einmal rebuilden, um Playwright/Locust etc. reinzubekommen. (Wenn du willst, liefere ich dir als nächsten Schritt eine `docker-compose.override.yml`, die Browser vorinstalliert.)

---
