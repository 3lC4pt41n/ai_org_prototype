**Implementierungsplan**

Beseitigung aller Audit-Befunde

AI Org Prototype 2.0 — E2E Pipeline

*6 Sprints · 12 Wochen · 33 Befunde · 67 Tickets*

Datum: 29. März 2026

**Inhaltsverzeichnis**

**1. Executive Summary**

Dieser Plan beschreibt die systematische Beseitigung aller 33 Befunde aus dem E2E-Pipeline-Audit. Die Befunde sind nach Abhängigkeiten geordnet: Infrastruktur-Fixes zuerst, dann Logik-Fixes, dann UX-Verbesserungen.

|  |  |
|----|----|
| **Parameter** | **Wert** |
| Zeitraum | 12 Wochen (6 Sprints à 2 Wochen) |
| Gesamtaufwand | 120–140 Personentage |
| Teamgröße empfohlen | 3–4 Backend-Devs + 1 Frontend-Dev + 1 QA |
| Kritische Befunde | 19 von 33 (alle in Sprint 1–4 adressiert) |
| Blockierend für Vollautomatisierung | 25 von 33 |
| MVP (Single-Agent stabil) | Sprint 1–4 (8 Wochen) |
| Vollständiger Multi-Agent-Betrieb | Sprint 1–6 (12 Wochen) |

**1.1 Kritischer Pfad**

Die längste Abhängigkeitskette bestimmt die Mindestdauer. Dieser kritische Pfad kann nicht parallelisiert werden:

DB-Migration (9.1) → CASCADE-FKs (9.2/9.3) → Celery-Timeouts (4.1/4.2) → Race-Conditions (1.1) → Deadlock-Recovery (1.2) → Artifact-Validierung (1.3) → Approval-Gates (6.1) → Feedback-Loop (6.2) → Multi-Agent-Merge (7.2) → Build-Check (8.1)

**1.2 Parallelisierbare Cluster**

Diese Arbeitspakete sind unabhängig vom kritischen Pfad und können parallel bearbeitet werden:

Cluster A (LLM): 5.1, 5.2, 5.3, 5.4 — komplett unabhängig, eigener Entwickler möglich

Cluster B (Neo4j): 3.2, 3.3 — unabhängig von Orchestrator-Fixes

Cluster C (Frontend): 10.1, 10.2 — Frontend-Entwickler parallel

Cluster D (Schema): 2.2, 2.3 — Artifact-Resolver und Schema-Validierung

**2. Abhängigkeitsgraph**

Die Pfeile zeigen: A → B bedeutet „A muss VOR B fertig sein“.

**2.1 Layer-Modell (9 Schichten)**

|  |  |  |  |
|----|----|----|----|
| **Layer** | **Name** | **Befunde** | **Begründung** |
| L0 | DB-Fundament | 9.1 Migration Chain | Alles andere braucht valides Schema |
| L1 | DB-Integrität | 9.2 CASCADE TaskDep, 9.3 CASCADE Tenant | FK-Constraints vor Business-Logik |
| L2 | Async-Sicherheit | 4.1 Timeouts, 4.2 Idempotenz, 4.3 Redis | Stabile Task-Ausführung als Basis |
| L3 | Orchestrator-Kern | 1.1 Race Cond., 1.2 Deadlock, 3.1 Stuck Tasks | Zuverlässige Phasenübergänge |
| L4 | Dateninteg. | 1.3 Leere Artifacts, 2.1 Kontext, 2.2–2.4 | Valide Daten zwischen Agents |
| L5 | LLM-Resilienz | 5.1–5.4 Error/Retry/Budget/Fallback | Stabile LLM-Aufrufe (parallel) |
| L6 | Gates+Feedback | 6.1–6.3, 1.4, 1.5 | Approval- und Feedback-Flows |
| L7 | Multi-Agent | 7.1–7.5, 4.4 | Koordination paralleler Agents |
| L8 | Output+UX | 8.1–8.3, 10.1, 10.2 | Finaler Output und Frontend |

**2.2 Blockierende Abhängigkeiten (Detail)**

9.1 → 9.2, 9.3 (Schema muss erst konsolidiert sein)

9.2 → 1.2 (Deadlock-Recovery braucht CASCADE für Cleanup)

4.1 → 3.1, 1.2 (Timeouts sind Voraussetzung für Stuck-Task-Recovery)

4.2 → 1.1 (Idempotenz vor Race-Condition-Fix, sonst doppelte Side-Effects)

1.1 → 1.2, 1.3 (Race-Condition-Schutz vor Orchestrator-Logic-Fixes)

1.3 → 2.1 (Artifact-Validierung vor Kontext-Erweiterung)

2.1 → 6.1 (Kumulativer Kontext benötigt für sinnvolle Approval-Validierung)

6.1 → 6.2 (Approval-Gates müssen funktionieren bevor Feedback-Loop Sinn macht)

6.2 → 7.4 (Feedback-Infrastruktur für Multi-Round Review)

7.5 → 7.1, 7.2, 7.3 (Shared Contracts vor paralleler Code-Generierung)

7.2 → 8.1, 8.2 (Merge-Mechanismus vor Validierung der Zusammenführung)

5.2 → 5.1 (backoff required bevor Error-Handling darauf aufbaut)

**3. Sprint-Plan**

**Sprint 1: Database Foundation + Async Safety (Woche 1–2)**

Ziel: Stabiles DB-Schema und sichere Task-Ausführung. Ohne dieses Fundament ist jeder andere Fix fragil.

**Workstream A: Datenbank (1 Dev)**

|  |  |  |  |  |  |
|----|----|----|----|----|----|
| **\#** | **Ticket** | **Befund** | **Größe** | **Prio** | **Abhängigkeiten** |
| S1-01 | Alembic-Verzeichnisse konsolidieren | 9.1 | L | P0 | Keine |
| S1-02 | Einheitliche Root-Migration erstellen | 9.1 | M | P0 | S1-01 |
| S1-03 | CASCADE DELETE auf TaskDependency FKs | 9.2 | S | P0 | S1-02 |
| S1-04 | CASCADE DELETE auf alle tenant_id FKs | 9.3 | M | P0 | S1-02 |
| S1-05 | Manuelle Kaskadierungs-Logik entfernen | 9.3 | S | P1 | S1-04 |
| S1-06 | Alembic fresh-DB Test schreiben | 9.1 | S | P1 | S1-02 |

**Workstream B: Celery/Async (1 Dev, parallel)**

|  |  |  |  |  |  |
|----|----|----|----|----|----|
| **\#** | **Ticket** | **Befund** | **Größe** | **Prio** | **Abhängigkeiten** |
| S1-07 | task_soft_time_limit + task_time_limit setzen | 4.1 | S | P0 | Keine |
| S1-08 | Rollenspezifische Timeouts (Planner=900s) | 4.1 | S | P0 | S1-07 |
| S1-09 | Idempotency-Key pro Task-Execution | 4.2 | M | P0 | Keine |
| S1-10 | Pre-Registration Artifact-Duplicate-Check | 4.2 | S | P0 | S1-09 |
| S1-11 | Redis broker_transport_options konfigurieren | 4.3 | S | P0 | Keine |
| S1-12 | Redis Health-Check vor Dispatch | 4.3 | S | P1 | S1-11 |
| S1-13 | backoff als required dependency | 5.2 | S | P0 | Keine |

Sprint 1 Kapazität: 13 Tickets, ~20 Personentage. Zwei Devs parallel, einer DB, einer Async.

**Sprint 2: Orchestrator Hardening (Woche 3–4)**

Ziel: Race Conditions beseitigen, Deadlock-Recovery, Stuck-Task-Detection. Nach diesem Sprint läuft die Pipeline stabil durch einzelne Phasen.

**Workstream A: Orchestrator (1–2 Devs)**

|  |  |  |  |  |  |
|----|----|----|----|----|----|
| **\#** | **Ticket** | **Befund** | **Größe** | **Prio** | **Abhängigkeiten** |
| S2-01 | Redis-Lock für Phasenübergänge einführen | 1.1 | M | P0 | S1-09 |
| S2-02 | Frische DB-Session pro Scheduler-Zyklus | 1.1 | S | P0 | Keine |
| S2-03 | Optimistic Locking (Version-Counter) auf Task | 1.1 | M | P0 | S2-02 |
| S2-04 | Stuck-Task-Detector Cronjob implementieren | 1.2, 3.1 | L | P0 | S1-07, S1-03 |
| S2-05 | Dead-Letter-Queue für nicht wiederherstellbare Tasks | 1.2 | M | P0 | S2-04 |
| S2-06 | Worker-Heartbeat-System implementieren | 3.1 | M | P1 | S2-04 |
| S2-07 | Orchestrator Integration-Test (Happy Path) | 1.1, 1.2 | L | P1 | S2-05 |

**Workstream B: LLM-Resilienz (1 Dev, parallel)**

|  |  |  |  |  |  |
|----|----|----|----|----|----|
| **\#** | **Ticket** | **Befund** | **Größe** | **Prio** | **Abhängigkeiten** |
| S2-08 | Differenziertes Error-Handling (429/500/401) | 5.1 | M | P0 | S1-13 |
| S2-09 | Exponential Backoff mit max 5 Retries, 5min Cap | 5.1 | M | P0 | S2-08 |
| S2-10 | Token-Budget-Reservation Pre-Call | 5.3 | M | P1 | Keine |
| S2-11 | tiktoken für präzise Token-Zählung | 5.3 | S | P1 | S2-10 |
| S2-12 | Fallback-Model-Chain pro Provider | 5.4 | M | P2 | S2-08 |

Sprint 2 Kapazität: 12 Tickets, ~22 Personentage. Zwei Workstreams parallel.

**Sprint 3: Data Integrity + Context Chain (Woche 5–6)**

Ziel: Valide Artifacts, kumulativer Kontext für alle Agents, einheitlicher Artifact-Resolver. Nach diesem Sprint liefert jeder Agent sinnvolle Ergebnisse.

**Workstream A: Artifact Integrity (1–2 Devs)**

|  |  |  |  |  |  |
|----|----|----|----|----|----|
| **\#** | **Ticket** | **Befund** | **Größe** | **Prio** | **Abhängigkeiten** |
| S3-01 | Content-Validierung in register_artefact() | 1.3 | M | P0 | S2-03 |
| S3-02 | Mindestlänge + Typ-spezifische Prüfung | 1.3 | S | P0 | S3-01 |
| S3-03 | Zentraler Artifact-Resolver: load_by_phase() | 2.3 | M | P0 | Keine |
| S3-04 | Alle Agents auf Artifact-Resolver umstellen | 2.3 | L | P0 | S3-03 |
| S3-05 | Planner JSON-Schema erweitern (bounds, refs) | 2.2 | M | P1 | Keine |
| S3-06 | Zyklen-Erkennung (DFS) nach Schema-Valid. | 3.3 | M | P1 | S3-05 |

**Workstream B: Kumulativer Kontext (1 Dev, parallel)**

|  |  |  |  |  |  |
|----|----|----|----|----|----|
| **\#** | **Ticket** | **Befund** | **Größe** | **Prio** | **Abhängigkeiten** |
| S3-07 | load_cumulative_context(purpose_id) Service | 2.1 | L | P0 | S3-03 |
| S3-08 | Architect: Vision + PRD als Kontext einbinden | 2.1 | M | P0 | S3-07 |
| S3-09 | Planner: PRD + Architecture als Kontext | 2.1 | M | P0 | S3-07 |
| S3-10 | Dev-Agent: Architecture Blueprint einbinden | 2.1 | M | P0 | S3-07 |
| S3-11 | Reviewer: PRD-Alignment prüfbar machen | 2.1 | S | P1 | S3-07 |
| S3-12 | Artifact-Versionierung (version_number, parent) | 2.4 | L | P2 | S3-03 |

**Workstream C: Neo4j Sync (1 Dev, parallel)**

|  |  |  |  |  |  |
|----|----|----|----|----|----|
| **\#** | **Ticket** | **Befund** | **Größe** | **Prio** | **Abhängigkeiten** |
| S3-13 | Graph-Sync als Celery-Task mit Retry | 3.2 | M | P1 | S1-11 |
| S3-14 | Periodischer Sync-Abgleich-Job | 3.2 | M | P2 | S3-13 |

Sprint 3 Kapazität: 14 Tickets, ~24 Personentage. Drei Workstreams parallel.

**Sprint 4: Approval-Gates + Feedback-Loop (Woche 7–8)**

Ziel: Lückenlose Approval-Gates, funktionierender Feedback-Loop mit Downstream-Invalidierung. Nach diesem Sprint ist die Pipeline im Single-Agent-Modus vollautomatisierungsfähig.

**⚠️ MEILENSTEIN: MVP — Single-Agent End-to-End stabil**

**Workstream A: Approval + Phase-Enforcement (1–2 Devs)**

|  |  |  |  |  |  |
|----|----|----|----|----|----|
| **\#** | **Ticket** | **Befund** | **Größe** | **Prio** | **Abhängigkeiten** |
| S4-01 | Zentrale approve_artifact() Service-Funktion | 6.3 | M | P0 | Keine |
| S4-02 | Alle 3 Endpoints auf approve_artifact() umstellen | 6.3 | M | P0 | S4-01 |
| S4-03 | Idempotency-Token für Approvals | 6.3 | S | P0 | S4-01 |
| S4-04 | requires_approval Feld enforced im Dispatcher | 1.5, 6.1 | M | P0 | S2-01 |
| S4-05 | Review-Hook: Blocker-Task mit TaskDependency | 6.1 | M | P0 | S4-04 |
| S4-06 | Position-Feld in Dispatcher-Sortierung nutzen | 1.4 | S | P1 | S2-01 |
| S4-07 | Transitive Vorgänger-Prüfung implementieren | 1.4 | M | P1 | S4-06 |

**Workstream B: Feedback-Loop (1 Dev, parallel)**

|  |  |  |  |  |  |
|----|----|----|----|----|----|
| **\#** | **Ticket** | **Befund** | **Größe** | **Prio** | **Abhängigkeiten** |
| S4-08 | Downstream-Invalidierung nach Feedback | 6.2 | L | P0 | S3-12 |
| S4-09 | Agent-Re-Dispatch nach Feedback-Integration | 6.2 | L | P0 | S4-08 |
| S4-10 | Kaskadierende Invalidierung (Artifact Chain) | 6.2 | M | P0 | S4-08 |
| S4-11 | Feedback als Kontext im Agent-Prompt | 6.2 | M | P1 | S4-09 |

Sprint 4 Kapazität: 11 Tickets, ~20 Personentage.

**Sprint 5: Multi-Agent Coordination (Woche 9–10)**

Ziel: Parallele Dev-Agents arbeiten koordiniert, Code Review ist blockierend, Merge-Mechanismus funktioniert. Nach diesem Sprint ist die volle Multi-Agent-Pipeline einsatzbereit.

**Workstream A: Shared Contracts + Dev-Coordination (2 Devs)**

|  |  |  |  |  |  |
|----|----|----|----|----|----|
| **\#** | **Ticket** | **Befund** | **Größe** | **Prio** | **Abhängigkeiten** |
| S5-01 | Shared Constraints Document Generator | 7.5 | XL | P0 | S3-07 |
| S5-02 | OpenAPI-Spec aus Architecture Blueprint | 7.5 | L | P0 | S5-01 |
| S5-03 | File-Ownership-Registry (path → task_id) | 7.1, 8.2 | M | P0 | Keine |
| S5-04 | Pre-Write Conflict-Detection | 8.2 | M | P0 | S5-03 |
| S5-05 | Peer-Task-Awareness in Dev-Agent Prompt | 7.1 | M | P0 | S5-03 |
| S5-06 | Queue-Registry + Dispatch-Validierung | 4.4 | M | P1 | Keine |

**Workstream B: Code Review + Merge (1–2 Devs, parallel)**

|  |  |  |  |  |  |
|----|----|----|----|----|----|
| **\#** | **Ticket** | **Befund** | **Größe** | **Prio** | **Abhängigkeiten** |
| S5-07 | Strukturiertes Review-Output (JSON Schema) | 7.3 | M | P0 | Keine |
| S5-08 | Review → Fix-Task bei critical issues | 7.3 | L | P0 | S5-07 |
| S5-09 | Re-Review nach Fix (max 3 Iterationen) | 7.4 | L | P0 | S5-08, S4-09 |
| S5-10 | AST-basierter Merge für Python | 7.2 | XL | P0 | S5-04 |
| S5-11 | Git-Merge-Fallback für nicht-Python Dateien | 7.2 | L | P1 | S5-10 |
| S5-12 | Merge-Conflict-Report als Artifact | 7.2 | S | P1 | S5-10 |

Sprint 5 Kapazität: 12 Tickets, ~26 Personentage. Größter Sprint (XL-Tickets).

**Sprint 6: Output Validation + UX Polish (Woche 11–12)**

Ziel: Generierter Code wird validiert, Frontend zeigt Echtzeit-Status. Die Pipeline ist vollständig produktionsreif.

**✅ MEILENSTEIN: Vollautomatisierung Multi-Agent E2E**

**Workstream A: Build-Validierung (1 Dev)**

|  |  |  |  |  |  |
|----|----|----|----|----|----|
| **\#** | **Ticket** | **Befund** | **Größe** | **Prio** | **Abhängigkeiten** |
| S6-01 | Post-Composition Syntax-Check (ast.parse, eslint) | 8.1 | L | P0 | S5-10 |
| S6-02 | Dependency-Check (pip check, npm audit) | 8.1 | M | P1 | S6-01 |
| S6-03 | Auto-gen requirements.txt aus Imports | 8.3 | M | P1 | S6-01 |
| S6-04 | Auto-gen Dockerfile aus Tech-Stack | 8.3 | M | P2 | S6-03 |
| S6-05 | Validation-Report als Artifact speichern | 8.1 | S | P1 | S6-01 |

**Workstream B: Frontend (1 Frontend-Dev, parallel)**

|  |  |  |  |  |  |
|----|----|----|----|----|----|
| **\#** | **Ticket** | **Befund** | **Größe** | **Prio** | **Abhängigkeiten** |
| S6-06 | Phase-Config von API laden statt hardcoded | 10.1 | M | P1 | S4-06 |
| S6-07 | WebSocket-Endpoint /ws/purposes/:id/status | 10.2 | L | P2 | Keine |
| S6-08 | Frontend WS-Subscription mit Auto-Reconnect | 10.2 | M | P2 | S6-07 |
| S6-09 | Auto-Mode Fortschrittsanzeige | 10.2 | S | P2 | S6-08 |

**Workstream C: E2E-Validierung (QA, parallel)**

|  |  |  |  |  |  |
|----|----|----|----|----|----|
| **\#** | **Ticket** | **Befund** | **Größe** | **Prio** | **Abhängigkeiten** |
| S6-10 | E2E-Test: Purpose → ZIP (Auto-Mode) | Alle | XL | P0 | S6-01 |
| S6-11 | E2E-Test: Feedback-Loop → Regenerierung | 6.2 | L | P1 | S4-09 |
| S6-12 | E2E-Test: Worker-Crash → Recovery | 1.2, 3.1 | L | P1 | S2-04 |
| S6-13 | E2E-Test: Budget-Limit → Graceful Stop | 5.3 | M | P2 | S2-10 |

Sprint 6 Kapazität: 13 Tickets, ~20 Personentage.

**4. Gesamtübersicht: Timeline**

|  |  |  |  |  |
|----|----|----|----|----|
| **Sprint** | **Fokus** | **Tickets** | **PT** | **Meilenstein** |
| 1 (W1–2) | DB + Async Safety | 13 | 20 | — |
| 2 (W3–4) | Orchestrator + LLM | 12 | 22 | — |
| 3 (W5–6) | Data Integrity + Context | 14 | 24 | — |
| **4 (W7–8)** | **Approval + Feedback** | **11** | **20** | **★ MVP Single-Agent** |
| 5 (W9–10) | Multi-Agent Coord. | 12 | 26 | — |
| **6 (W11–12)** | **Output + UX + E2E** | **13** | **20** | **★ Vollautomatisierung** |
| TOTAL |  | 75 | 132 |  |

**5. Risiken & Mitigationen**

|  |  |  |  |
|----|----|----|----|
| **Risiko** | **Wahrsch.** | **Impact** | **Mitigation** |
| AST-Merge (S5-10) komplexer als geschätzt | Hoch | Sprint 5 verlängert sich | Fallback: Git-only Merge mit manueller Review-Queue |
| Migration 9.1 hat Datenverlust-Risiko | Mittel | Production-DB beschädigt | Staging-Test mandatory. DB-Backup vor Migration. |
| LLM-API-Änderungen während Sprint 2 | Niedrig | Retry-Logik muss angepasst werden | Provider-Abstraktionsschicht in S2-08 |
| Team kleiner als empfohlen (\< 4 Devs) | Mittel | Timeline verlängert auf 16–18 Wochen | MVP-Pfad priorisieren (Sprint 1–4 only) |
| Shared Constraints (S5-01) zu abstrakt | Mittel | Dev-Agents ignorieren Constraints | Evals mit 5 Test-Projekten vor Rollout |

**6. Empfohlene Teamstruktur**

|  |  |  |
|----|----|----|
| **Rolle** | **Sprints** | **Verantwortung** |
| DB/Backend Dev | 1–4 | Migrationen, CASCADE, Repo-Layer, Artifact-Resolver |
| Async/Infra Dev | 1–3 | Celery, Redis, Timeouts, Idempotenz, Neo4j Sync |
| Orchestrator Dev | 2–4 | Race Conditions, Locks, Stuck-Task, Approval-Gates |
| LLM/Agent Dev | 2–5 | Error-Handling, Kontext-Chain, Agent-Prompts, Merge |
| Frontend Dev | 6 | Phase-Config, WebSocket, Real-Time UI |
| QA Engineer | 4–6 | E2E-Tests, Regression, Edge Cases, Load Tests |

**6.1 MVP-Pfad (reduziertes Team)**

Bei nur 2 Entwicklern: Sprint 1–4 in 10–12 Wochen statt 8. Sprint 5–6 verschieben. Single-Agent-Modus wird stabil, Multi-Agent später. Kritischste 25 Befunde werden in 10 Wochen beseitigt.

**7. Definition of Done pro Sprint**

**Sprint 1: DB + Async**

• Alembic alembic upgrade head auf frischer DB fehlerfrei

• CASCADE-Löschung: Tenant löschen → alle abhängigen Records weg

• Celery-Task mit time_limit: Worker killed nach Timeout

• Doppelter Task-Dispatch: Nur ein Artifact entsteht

**Sprint 2: Orchestrator + LLM**

• Gleichzeitiger Scheduler + Worker: Kein doppeltes Status-Update

• Stuck-Task (\>30min doing): Automatisch auf failed gesetzt

• LLM 429 Error: 3x Retry mit Backoff, dann fail

• Integration-Test: Phase 1→5 durchläuft fehlerfrei (Single-Agent)

**Sprint 3: Data Integrity**

• Leeres Artifact: register_artefact() wirft ValidationError

• Architect-Prompt enthält Vision + PRD Kontext

• Dev-Agent-Prompt enthält Architecture Blueprint

• Planner: Zyklischer Graph → ValidationError

**Sprint 4: Approval + Feedback**

• Manual-Mode: Phase startet nicht ohne Approval

• PRD-Feedback: Architecture wird automatisch re-generiert

• Auto-Mode: Purpose → Implementation ohne menschliches Eingreifen

**Sprint 5: Multi-Agent**

• 3 Dev-Agents: Keine Datei wird doppelt geschrieben

• Code Review mit critical issue: Fix-Task wird erstellt

• Shared Constraints: Alle Agents nutzen gleiche API-Spec

**Sprint 6: Output + E2E**

• Generiertes Python: ast.parse() fehlerfrei

• Auto-generated requirements.txt vorhanden

• Frontend: Phase-Status aktualisiert sich live (\< 3s Latenz)

• E2E: Purpose → ZIP dauert \< 15 Minuten (Single-Agent)
