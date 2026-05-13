# E2E Pipeline Audit – AI Org Prototype 2.0

## Systemkontext

Du bist ein Senior Software Architect mit Expertise in verteilten Systemen, LLM-Orchestrierung und autonomer Softwareerstellung. Du auditierst das Repository `ai_org_prototype` – eine Plattform, die vollautomatische Softwareerstellung durch eine Pipeline von LLM-Agenten ermöglicht.

## Ziel

Führe ein vollständiges End-to-End-Audit der gesamten Pipeline durch. Identifiziere **Bruchstellen**, **Inkonsistenzen**, **fehlende Absicherungen** und **architektonische Schwächen**, die verhindern, dass der Flow zuverlässig und vollautomatisch von der Projekteingabe bis zum fertigen, auslieferbaren Softwareprodukt durchläuft.

---

## Der Soll-Flow (Erwartete Pipeline)

```
┌─────────────────────────────────────────────────────────────────────┐
│  USER: Projektziel / Purpose eingeben                               │
│    ↓                                                                │
│  PHASE 1 — LLM Vision Agent                                        │
│    → Generiert Vision Document (Zielgruppe, Problem, Erfolgs-       │
│      kriterien, Differenzierung, Risiken)                           │
│    → [FREIGABE-GATE]                                                │
│    ↓                                                                │
│  PHASE 2 — LLM Product Owner Agent (PRD)                           │
│    → Generiert Product Requirements Document (Features, User        │
│      Stories, Akzeptanzkriterien, Priorisierung)                    │
│    → [FREIGABE-GATE]                                                │
│    ↓                                                                │
│  PHASE 3 — LLM Architect Agent                                     │
│    → Generiert Architecture Blueprint (Systemarchitektur, Domain    │
│      Model, Tech Stack, API-Design, Datenmodell)                    │
│    → [FREIGABE-GATE]                                                │
│    ↓                                                                │
│  PHASE 4 — LLM Architecture & Domain Review Agent                  │
│    → Überprüft Architecture Blueprint auf Konsistenz, Skalierbar-   │
│      keit, Domain-Korrektheit, Security, Machbarkeit                │
│    → [FREIGABE-GATE]                                                │
│    ↓                                                                │
│  PHASE 5 — LLM Planner Agent                                       │
│    → Zerlegt PRD + Architecture in konkrete Implementierungs-Tasks  │
│    → Erzeugt DAG (Abhängigkeitsgraph) in Neo4j + PostgreSQL        │
│    → [FREIGABE-GATE]                                                │
│    ↓                                                                │
│  PHASE 6 — Implementation (Parallel, Multi-Agent)                   │
│    ├── Dev Agent 1 → Code-Generierung → [Code Review]              │
│    ├── Dev Agent 2 → Code-Generierung → [Code Review]              │
│    ├── Dev Agent 3 → Code-Generierung → [Code Review]              │
│    ├── QA Agent → Test-Generierung                                  │
│    ├── UX/UI Agent → Frontend-Design                                │
│    └── Integration/E2E Agent → Integrationstests                    │
│    ↓                                                                │
│  PHASE 7 — Gesamt-Review & Release                                  │
│    → Finaler Review aller Artifacts                                  │
│    → Repo Composer aggregiert alle Outputs                          │
│    → ZIP-Export / Deployment                                         │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Audit-Aufgaben

Analysiere die folgenden Bereiche **systematisch** und **dateibasiert**. Referenziere immer die konkreten Dateien und Zeilennummern.

### 1. Orchestrator & Phase-Transitions

**Dateien:** `backend/ai_org_backend/orchestrator/scheduler.py`, `orchestrator/core.py`, `orchestrator/graph_orchestrator.py`

- Wie erkennt der Orchestrator, dass eine Phase abgeschlossen ist und die nächste beginnen soll?
- Ist der Phasenübergang (Vision → PRD → Architecture → Review → Planner → Implementation → Release) **deterministisch und lückenlos** implementiert?
- Gibt es Race Conditions zwischen dem Scheduler-Loop und Celery-Worker-Callbacks?
- Was passiert, wenn ein Agent **kein Artifact** produziert (leere Antwort, Timeout, LLM-Fehler)?
- Wie wird das Freigabe-Gate (`requires_approval`) zwischen Auto- und Manual-Modus umgesetzt?
- Existiert ein **Deadlock-Szenario**, in dem der Orchestrator auf eine Bedingung wartet, die nie eintritt?
- Wird die Phase-Reihenfolge über `PipelinePhase.position` und `predecessor_id` enforced, oder gibt es Wege, Phasen zu überspringen?

### 2. Agent-zu-Agent-Datenfluss (Artifact Chain)

**Dateien:** `agents/vision.py`, `agents/product_owner.py`, `agents/architect.py`, `agents/reviewer.py`, `agents/planner.py`, `agents/agent_dev.py`, `agents/code_review.py`, `agents/repo_composer.py`

- Wie wird das **Output von Phase N** als **Input für Phase N+1** weitergegeben?
- Werden Artifacts über die Datenbank (Artifact-Tabelle) geladen oder direkt aus dem Dateisystem (`workspace/`)?
- Gibt es eine **Schema-Validierung** der Agent-Outputs? Was passiert, wenn der Planner kein valides JSON liefert?
- Ist die **Prompt-Kette** konsistent? Erwartet der Architect-Prompt das exakte Format, das der PRD-Agent produziert?
- Wie werden die **Jinja2-Templates** (`prompts/*.j2`) mit den Artifact-Inhalten befüllt? Gibt es Template-Variablen, die nie gesetzt werden?
- Wird der **Kontext** (Vision + PRD + Architecture) kumulativ an spätere Agents weitergegeben, oder geht Information verloren?

### 3. Task-Graph & Dependency Resolution (Neo4j + PostgreSQL)

**Dateien:** `orchestrator/graph_orchestrator.py`, `services/graph_sync.py`, `models/task.py`, `models/task_dependency.py`, `repo.py`

- Ist die **bidirektionale Synchronisation** zwischen PostgreSQL und Neo4j zuverlässig? Was passiert bei Sync-Fehlern?
- Kann der Task-Graph **zyklische Abhängigkeiten** enthalten? Gibt es eine Validierung?
- Wie werden "ready tasks" (LEAF_Q) identifiziert? Kann es passieren, dass ein Task nie "ready" wird?
- Was passiert, wenn ein Task im Status `doing` hängen bleibt (Worker-Crash, OOM)?
- Gibt es einen **Retry-Mechanismus** mit Backoff für fehlgeschlagene Tasks?
- Wie wird die **Konsistenz** zwischen `task.status` in PostgreSQL und dem Neo4j-Graph sichergestellt?

### 4. Celery Worker & Task Execution

**Dateien:** `tasks/celery_app.py`, `tasks/llm_tasks.py`, `tasks/dynamic_worker.py`, `orchestrator/executor.py`, `orchestrator/router.py`

- Wie wird ein Task dem richtigen Worker/Agent zugeordnet (Role Routing)?
- Was passiert bei **Worker-Starvation** (z.B. alle Dev-Worker belegt, neue Tasks warten endlos)?
- Gibt es **Task-Timeouts** auf Celery-Ebene? Wie wird ein Timeout behandelt?
- Wie wird **Idempotenz** sichergestellt? Kann ein Task doppelt ausgeführt werden?
- Was passiert, wenn der Redis-Broker kurzzeitig nicht erreichbar ist?
- Sind die **Queue-Namen** (`{tenant_id}:{role}`) konsistent zwischen Dispatcher und Worker-Config?

### 5. LLM-Integration & Fehlerbehandlung

**Dateien:** `services/llm_client.py`, `agents/utils.py`, `config.py`

- Wie wird mit **LLM-API-Fehlern** umgegangen (Rate Limits, 500er, Timeouts, Context-Length-Overflow)?
- Gibt es **Retry-Logik mit Exponential Backoff** für LLM-Calls?
- Wie wird die **Token-Budget-Enforcement** umgesetzt? Was passiert, wenn ein Agent das Budget überschreitet?
- Werden **Streaming-Responses** verwendet oder synchrone Calls? Gibt es Timeout-Risiken bei langen Generierungen?
- Wie wird das **Modell pro Task** ausgewählt? Ist die Konfiguration (`model_name` in PipelinePhase) durchgängig?
- Gibt es **Fallback-Modelle**, wenn das primäre Modell nicht verfügbar ist?

### 6. Approval-Gates & Feedback-Loop

**Dateien:** `api/artifact_bridge.py`, `api/reviews.py`, `models/feedback.py`, `hooks/review_hook.py`, `api/chat.py`

- Ist der **Approval-Flow** lückenlos? Kann der Orchestrator eine Phase starten, obwohl die vorherige nicht freigegeben wurde?
- Wie wird **Feedback** (Ablehnung + Kommentar) an den Agent zurückgeführt? Wird der Agent erneut ausgeführt mit dem Feedback als zusätzlichem Kontext?
- Was passiert bei **partieller Freigabe** (z.B. PRD teilweise akzeptiert)?
- Funktioniert der **Auto-Modus** tatsächlich end-to-end ohne menschliches Eingreifen? Welche impliziten Annahmen gibt es?
- Sind die WebSocket-/REST-Endpunkte für Approval konsistent und synchronisiert?

### 7. Implementation Phase – Multi-Agent Coordination

**Dateien:** `agents/agent_dev.py`, `agents/agent_qa.py`, `agents/agent_ux_ui.py`, `agents/code_review.py`, `agents/e2e.py`, `agents/agent_integration.py`

- Wie wird sichergestellt, dass **Dev1, Dev2, Dev3** nicht denselben Code in widersprüchlicher Weise generieren?
- Gibt es einen **Merge-Mechanismus** für parallele Code-Generierung? Wie werden Konflikte aufgelöst?
- Wie funktioniert der **Code Review** zwischen Agents? Kann ein Review-Agent tatsächlich den Code eines Dev-Agents bewerten und Änderungen einfordern?
- Ist der **Feedback-Loop** (Review → Rework → Re-Review) implementiert oder nur ein Single-Pass?
- Wie wird die **Gesamtkonsistenz** des generierten Codes sichergestellt (gemeinsame Imports, Interfaces, API-Contracts)?
- Kennen die Dev-Agents die **Outputs der anderen Dev-Agents**, oder arbeiten sie isoliert?

### 8. Repo Composer & Artifact Aggregation

**Dateien:** `agents/repo_composer.py`, `services/storage.py`, `services/artifact_workflow.py`

- Wie werden alle Einzelartefakte zu einem **kohärenten Repository** zusammengesetzt?
- Gibt es eine **Validierung** des Gesamtergebnisses (Syntax-Check, Dependency-Check, Build-Test)?
- Wie werden **Dateikonflikte** behandelt (zwei Agents schreiben in dieselbe Datei)?
- Wird eine `package.json` / `requirements.txt` / `Dockerfile` automatisch generiert?
- Ist der **ZIP-Export** (`/api/project.zip`) funktionsfähig und vollständig?

### 9. Datenbank-Konsistenz & Migrations

**Dateien:** `models/*.py`, `migrations/versions/*.py`, `db.py`, `repo.py`

- Sind alle **Alembic-Migrations** linear und ohne Konflikte?
- Stimmen die **SQLModel-Definitionen** mit dem tatsächlichen DB-Schema überein?
- Gibt es **Foreign-Key-Constraints**, die bei der Pipeline-Ausführung verletzt werden könnten?
- Wie werden **Transaktionen** behandelt? Gibt es Szenarien mit inkonsistenten Zuständen?

### 10. Frontend-Backend-Synchronisation

**Dateien:** `frontend/apps/web/src/components/pipeline/phases/*.tsx`, `frontend/apps/web/src/pages/PipelinePage.tsx`, `api/pipeline.py`, `api/purposes.py`

- Spiegelt das Frontend **alle Pipeline-Phasen** korrekt wider?
- Sind die **Phase-Slugs** zwischen Frontend (`phaseConfig.ts`) und Backend (`PipelinePhase.slug`) identisch?
- Wie wird der **Echtzeit-Status** synchronisiert (Polling, WebSocket, SSE)?
- Kann der User im Frontend den **Auto-Modus** aktivieren und sieht er dann den Fortschritt in Echtzeit?

---

## Output-Format

Strukturiere dein Audit wie folgt:

```markdown
## Audit-Ergebnis: [Bereich]

### Befund [Nummer]: [Kurztitel]
- **Schweregrad:** 🔴 Kritisch | 🟡 Mittel | 🟢 Niedrig
- **Dateien:** [Betroffene Dateien mit Pfad]
- **Beschreibung:** [Was ist das Problem?]
- **Impact:** [Wie wirkt sich das auf den E2E-Flow aus?]
- **Evidenz:** [Code-Snippet oder Logik-Referenz]
- **Empfehlung:** [Konkreter Fix mit Pseudo-Code oder Architektur-Vorschlag]
```

### Zusammenfassung

Erstelle am Ende eine **Risikomatrix** mit:

| # | Befund | Schweregrad | Phase | Blockierend für Vollautomatisierung? |
|---|--------|-------------|-------|--------------------------------------|
| 1 | ...    | 🔴          | ...   | Ja/Nein                              |

Sowie eine **priorisierte Empfehlungsliste** (Top 10), geordnet nach Impact auf die Vollautomatisierung.

---

## Kontext-Dateien für das Audit

Lies und analysiere mindestens die folgenden Dateien:

### Orchestrator-Kern
- `backend/ai_org_backend/orchestrator/scheduler.py`
- `backend/ai_org_backend/orchestrator/core.py`
- `backend/ai_org_backend/orchestrator/graph_orchestrator.py`
- `backend/ai_org_backend/orchestrator/executor.py`
- `backend/ai_org_backend/orchestrator/router.py`

### Agents (alle Phasen)
- `backend/ai_org_backend/agents/vision.py`
- `backend/ai_org_backend/agents/product_owner.py`
- `backend/ai_org_backend/agents/architect.py`
- `backend/ai_org_backend/agents/reviewer.py`
- `backend/ai_org_backend/agents/planner.py`
- `backend/ai_org_backend/agents/agent_dev.py`
- `backend/ai_org_backend/agents/agent_qa.py`
- `backend/ai_org_backend/agents/code_review.py`
- `backend/ai_org_backend/agents/repo_composer.py`
- `backend/ai_org_backend/agents/utils.py`

### Prompt-Templates
- `prompts/vision.j2`
- `prompts/requirements.j2`
- `prompts/architect.j2`
- `prompts/review.j2`
- `prompts/planner.j2`
- `prompts/dev.j2`
- `prompts/code_review.j2`
- `prompts/repo_composer.j2`

### Datenmodelle & Services
- `backend/ai_org_backend/models/task.py`
- `backend/ai_org_backend/models/pipeline.py`
- `backend/ai_org_backend/models/artifact.py`
- `backend/ai_org_backend/models/feedback.py`
- `backend/ai_org_backend/services/llm_client.py`
- `backend/ai_org_backend/services/storage.py`
- `backend/ai_org_backend/services/graph_sync.py`
- `backend/ai_org_backend/services/artifact_workflow.py`
- `backend/ai_org_backend/services/budget.py`
- `backend/ai_org_backend/repo.py`

### API-Layer
- `backend/ai_org_backend/api/pipeline.py`
- `backend/ai_org_backend/api/purposes.py`
- `backend/ai_org_backend/api/artifact_bridge.py`
- `backend/ai_org_backend/api/reviews.py`

### Frontend (Phase-Konfiguration)
- `frontend/apps/web/src/components/pipeline/phaseConfig.ts`
- `frontend/apps/web/src/components/pipeline/phases/*.tsx`
- `frontend/apps/web/src/pages/PipelinePage.tsx`

---

## Wichtige Hinweise

1. **Nicht oberflächlich bleiben.** Lies den tatsächlichen Code, nicht nur Dateinamen. Verfolge den Datenfluss von der Purpose-Erstellung bis zum ZIP-Export.
2. **Teste Randfälle gedanklich durch:** Was passiert bei leerem LLM-Output? Bei doppeltem Approval? Bei Budget = 0 vor Phase 3?
3. **Bewerte den Auto-Modus separat.** Die Vollautomatisierung ist das Kernziel – jede Stelle, die implizit menschliches Eingreifen erfordert, ist ein kritischer Befund.
4. **Achte auf "tote Pfade"** – Code, der existiert, aber nie aufgerufen wird, oder Phasen, die in der Konfiguration definiert, aber im Orchestrator nicht behandelt werden.
5. **Prüfe die Prompt-Qualität** – Sind die Jinja2-Prompts präzise genug, um konsistente, maschinenlesbare Outputs zu erzwingen? Oder sind sie so offen, dass der Agent beliebigen Freitext produziert, den die nächste Phase nicht parsen kann?
