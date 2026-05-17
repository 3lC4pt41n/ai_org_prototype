**Implementation Master Plan**

ai_org_prototype – E2E Pipeline Fixes

25 Findings • 6 Sprints • Zero Kompromisse

30\. März 2026

*Dieses Dokument enthält den vollständigen, schrittweisen Implementierungsplan zur Lösung aller 25 Audit-Findings. Jeder Fix ist mit exakten Datei- und Zeilenreferenzen, konkretem Pseudo-Code, Abhängigkeiten, Testkriterien und Aufwandsschätzung versehen.*

Inhaltsverzeichnis

1\. Strategieübersicht

Der Plan gliedert sich in 6 Sprints à 2 Wochen. Die Sprints sind nach Abhängigkeiten und Impact-Priorität geordnet: Sprint 1 behebt die kritischsten Blocker für den Auto-Modus, Sprint 6 schließt mit Frontend-UX und Observability ab.

|  |  |  |  |  |  |
|----|----|----|----|----|----|
| **Sprint** | **Fokus** | **Prio** | **Findings** | **Dauer** | **Gate** |
| **S1** | Phase-Gate & Artifact Validation | **P0** | \#1, \#2, \#9, \#12 | 2 Wochen | Auto-Modus startet nicht ohne Artifacts |
| **S2** | Approval & Feedback Re-Execution | **P0** | \#4, \#5, \#13 | 2 Wochen | Feedback-Loop funktional |
| **S3** | Graph Integrity & Stuck-Task Recovery | **P0** | \#3, \#6, \#7, \#11 | 2 Wochen | Kein Deadlock möglich |
| **S4** | Multi-Agent Conflict Prevention & Validation | **P1** | \#8, \#10, \#23, \#25 | 2 Wochen | Generierter Code kompiliert |
| **S5** | LLM Resilience & Data Flow Hardening | **P1** | \#14, \#15, \#16, \#17, \#18, \#19 | 2 Wochen | Keine Silent Failures |
| **S6** | DB Migrations, Frontend & Observability | **P2** | \#20, \#21, \#22, \#24 | 2 Wochen | Echtzeit-UI, saubere DB |

Gesamtdauer: 12 Wochen (6 × 2-Wochen-Sprints). Jeder Sprint endet mit einem Acceptance-Gate, das die Weiterarbeit freigibt.

2\. Abhängigkeitsgraph der Fixes

Die folgende Matrix zeigt, welcher Fix welchen anderen voraussetzt. Fixes ohne Vorbedingung können parallel bearbeitet werden.

|  |  |  |  |
|----|----|----|----|
| **Fix** | **Titel** | **Hängt ab von** | **Sprint** |
| **\#1** | Phase-Gate Artifact Validation | Keine | S1 |
| **\#2** | requires_approval Enforcement | \#1 (Gate-Logik) | S1 |
| **\#9** | Artifact Fallback in Agents | \#1 (Validierung vorhanden) | S1 |
| **\#12** | Auto-Mode Approval Gap | \#1, \#2 | S1 |
| **\#5** | Zentralisierter Approval-Service | \#1, \#2 (Gate-Logik) | S2 |
| **\#4** | Feedback Re-Execution Loop | \#5 (Approval-Service) | S2 |
| **\#13** | Code Review Re-Review Loop | \#4 (Redispatch-Logik) | S2 |
| **\#6** | Graph Sync Retry & Reconciliation | Keine | S3 |
| **\#7** | Cycle Detection in repo.link() | \#6 (Graph stabil) | S3 |
| **\#11** | Stuck Task Watchdog | Keine | S3 |
| **\#3** | Race Condition Dispatch Lock | \#6, \#11 | S3 |
| **\#8** | File-Ownership Reservation | \#7 (DAG valide) | S4 |
| **\#23** | Peer Context Hard Constraints | \#8 (Reservierung) | S4 |
| **\#10** | Post-Assembly Build Validation | \#8 (kein Konflikt) | S4 |
| **\#25** | Planner Schema Hardening | Keine | S4 |
| **\#14** | Double Budget Debit Fix | Keine | S5 |
| **\#15** | LLM Retry via resilient_llm_call() | Keine | S5 |
| **\#16** | LLM Call Timeouts | \#15 | S5 |
| **\#17** | Jinja2 Template Validation | Keine | S5 |
| **\#18** | Truncation Warnings | Keine | S5 |
| **\#19** | Centralized Model Selector | \#15 (Retry-Integration) | S5 |
| **\#20** | Migration Chain Consolidation | Keine | S6 |
| **\#21** | Phase Slug Validation API | \#20 (Schema stabil) | S6 |
| **\#22** | Auto-Mode Backend Trigger | \#1, \#5 (Gates + Approval) | S6 |
| **\#24** | Echtzeit-Status via SSE/WebSocket | \#21 (API stabil) | S6 |

3\. Sprint 1: Phase-Gate & Artifact Validation

**Ziel:** Kein Phase-Übergang ohne validiertes Artifact. Die Grundvoraussetzung für jeden weiteren Fix.

|  |  |  |  |
|----|----|----|----|
| **Fix** | **Titel** | **Aufwand** | **Abhängigkeit** |
| **\#1** | Phase-Gate Artifact Validation erzwingen | 4h Implementierung + 4h Tests | Keine |
| **\#2** | requires_approval Dead-Code aktivieren | 2h Implementierung + 2h Tests | \#1 (Gate-Logik) |
| **\#9** | Artifact Fallback: Explizites Scheitern statt Silent None | 4h Implementierung + 3h Tests | \#1 (Validierung vorhanden) |
| **\#12** | Auto-Mode Approval Gap in review_hook.py schließen | 2h Implementierung + 2h Tests | \#1, \#2 |

\#1: Phase-Gate Artifact Validation erzwingen

**Dateien:** orchestrator/scheduler.py – Funktion \_generate_plan_for_purpose()

**Änderungen:**

- Zeile 396-401: vision_approved-Bedingung ändern. Statt purpose_mode == "auto" als alleinige Bedingung muss IMMER geprüft werden: vision_artifact is not None and len(vision_artifact.content or "") \> 0.

- Zeile 431: prd_ready_for_architecture – gleiches Muster: prd_artifact must exist AND have content.

- Zeile 445-447: blueprint_artifact-Check von "if purpose_mode == 'manual'" ändern zu: immer prüfen, ob blueprint_artifact existiert.

- Zeile 536-538: review_artifact-Check – identisches Muster.

**Code (Vorher/Nachher):**

> \# VORHER (Zeile 396-401):
>
> vision_approved = bool(
>
> purpose_mode == "auto"
>
> or (vision_artifact and vision_artifact.released)
>
> or "approved" in (vision_task.notes or "").lower()
>
> )
>
> \# NACHHER:
>
> vision_approved = bool(
>
> vision_artifact
>
> and len(vision_artifact.content or "") \> 0
>
> and (
>
> purpose_mode == "auto"
>
> or vision_artifact.released
>
> or "approved" in (vision_task.notes or "").lower()
>
> )
>
> )

**Testkriterium:** Unit-Test: Erstelle Purpose im Auto-Modus, setze Vision-Task auf DONE ohne Artifact. Erwarte: Pipeline bleibt stehen. Dann: Füge Artifact hinzu → Pipeline schreitet fort.

**Aufwand:** 4h Implementierung + 4h Tests

------------------------------------------------------------------------

\#2: requires_approval Dead-Code aktivieren

**Dateien:** orchestrator/scheduler.py – Funktion \_ready_for_execution() Zeile 97-100

**Änderungen:**

- Zeile 97-100: pass durch echte Validierung ersetzen.

- Wenn task.requires_approval True ist: Prüfe, ob das zugehörige Artifact existiert UND artifact.released == True.

- Falls nicht: return False (Task ist nicht ready).

**Code (Vorher/Nachher):**

> \# VORHER (Zeile 97-100):
>
> if task.requires_approval:
>
> pass \# Dead code
>
> \# NACHHER:
>
> if task.requires_approval:
>
> artifact = session.exec(
>
> select(Artifact)
>
> .where(Artifact.task_id == task.id)
>
> .order_by(Artifact.created_at.desc())
>
> ).first()
>
> if not artifact or not artifact.released:
>
> return False

**Testkriterium:** Test: Task mit requires_approval=True ohne released Artifact → \_ready_for_execution() gibt False zurück.

**Aufwand:** 2h Implementierung + 2h Tests

------------------------------------------------------------------------

\#9: Artifact Fallback: Explizites Scheitern statt Silent None

**Dateien:** services/artifact_resolver.py – Funktion load_by_phase() Zeile 56-99

**Änderungen:**

- Zeile 90-91: Wenn Task nicht gefunden → log.warning() + raise ArtifactNotFoundError(phase, purpose_id).

- Zeile 94-95: Wenn Artifact nicht gefunden → gleicher Fehler.

- Zeile 96-97: Wenn Artifact nicht released und require_released=True → log.warning() mit Details.

- Neue Exception-Klasse ArtifactNotFoundError in services/exceptions.py anlegen.

- In allen Agents (planner.py:276, agent_dev.py, architect.py): try/except um load_by_phase() – bei Fehler Task auf FAILED setzen mit beschreibender Nachricht.

**Code (Vorher/Nachher):**

> \# services/artifact_resolver.py - NACHHER:
>
> class ArtifactNotFoundError(Exception):
>
> def \_\_init\_\_(self, phase: str, purpose_id: str):
>
> super().\_\_init\_\_(f"Required artifact for phase '{phase}' not found (purpose={purpose_id})")
>
> def load_by_phase(self, phase: str, purpose_id: str, \*, require_released: bool = False):
>
> task = self.\_find_task(phase, purpose_id)
>
> if not task:
>
> log.warning("No task found for phase=%s purpose=%s", phase, purpose_id)
>
> raise ArtifactNotFoundError(phase, purpose_id)
>
> artifact = self.\_find_artifact(task.id)
>
> if not artifact:
>
> log.warning("No artifact for task=%s phase=%s", task.id, phase)
>
> raise ArtifactNotFoundError(phase, purpose_id)
>
> if require_released and not artifact.released:
>
> log.warning("Artifact %s not released", artifact.id)
>
> raise ArtifactNotFoundError(phase, purpose_id)
>
> return artifact

**Testkriterium:** Test: load_by_phase() für nicht-existente Phase → ArtifactNotFoundError. Planner mit fehlendem Blueprint → Task-Status FAILED.

**Aufwand:** 4h Implementierung + 3h Tests

------------------------------------------------------------------------

\#12: Auto-Mode Approval Gap in review_hook.py schließen

**Dateien:** hooks/review_hook.py – Funktion \_maybe_trigger_review() Zeile 155-171

**Änderungen:**

- Zeile 167: Die Bedingung if purpose_mode == "manual" and not blueprint_released umdrehen.

- Auch im Auto-Modus muss das Blueprint-Artifact existieren und Content haben.

- Neue Bedingung: if not blueprint_released and (purpose_mode == "manual" or not latest_blueprint_artifact): return

**Code (Vorher/Nachher):**

> \# VORHER (Zeile 167-171):
>
> if purpose_mode == "manual" and not blueprint_released:
>
> logging.info("\[ReviewHook\] Skip auto-review...")
>
> return
>
> \# NACHHER:
>
> if not latest_blueprint_artifact or not latest_blueprint_artifact.content:
>
> logging.warning("\[ReviewHook\] Blueprint artifact missing or empty for purpose=%s", purpose_id)
>
> return
>
> if purpose_mode == "manual" and not blueprint_released:
>
> logging.info("\[ReviewHook\] Skip auto-review – manual mode, blueprint not released")
>
> return

**Testkriterium:** Test: Auto-Modus ohne Blueprint-Artifact → Review wird NICHT getriggert. Auto-Modus MIT Blueprint → Review wird getriggert.

**Aufwand:** 2h Implementierung + 2h Tests

------------------------------------------------------------------------

**Sprint 1 Acceptance Gate:** Kein Phase-Übergang ohne validiertes Artifact. Die Grundvoraussetzung für jeden weiteren Fix.

4\. Sprint 2: Approval & Feedback Re-Execution

**Ziel:** Ein einziger Approval-Pfad. Feedback führt zu Agent-Re-Execution. Review-Loop schließt sich.

|  |  |  |  |
|----|----|----|----|
| **Fix** | **Titel** | **Aufwand** | **Abhängigkeit** |
| **\#5** | WebSocket Approval durch zentralen Service routen | 6h Implementierung + 4h Tests | \#1, \#2 (Gate-Logik) |
| **\#4** | Feedback Re-Execution Loop verdrahten | 4h Implementierung + 6h E2E-Tests | \#5 (Approval-Service) |
| **\#13** | Code Review Re-Review Loop automatisieren | 6h Implementierung + 4h Tests | \#4 (Redispatch-Logik) |

\#5: WebSocket Approval durch zentralen Service routen

**Dateien:** api/chat.py – Funktion websocket_chat() Zeile 825-879

**Änderungen:**

- Zeile 825-879: Den gesamten Block (if user_msg.intent == ChatIntent.APPROVAL) ersetzen.

- Statt direktem artifact.released = True den approval.approve_artifact() Service aufrufen.

- Import hinzufügen: from services.approval import approve_artifact

- Für jeden artifact_id: result = approve_artifact(aid, tenant_id=tenant_id, purpose_id=purpose_id, session=session).

- Pause-Flag Clearing passiert automatisch im Service (clear_pause=True default).

**Code (Vorher/Nachher):**

> \# VORHER (Zeile 825-879): Direkte Mutation
>
> artifact.released = True
>
> task.status = "done"
>
> pool.delete(f"pause:{tenant_id}:{purpose_id}")
>
> \# NACHHER:
>
> from ai_org_backend.services.approval import approve_artifact
>
> if user_msg.intent == ChatIntent.APPROVAL:
>
> results = \[\]
>
> for aid in artifact_ids:
>
> try:
>
> result = approve_artifact(
>
> aid,
>
> tenant_id=tenant_id,
>
> purpose_id=purpose_id,
>
> clear_pause=True,
>
> session=session,
>
> )
>
> results.append(result)
>
> except Exception as e:
>
> logger.error("Approval failed for artifact %s: %s", aid, e)
>
> \# Use phase_hint from results for downstream dispatch
>
> for r in results:
>
> if r and r.phase_hint:
>
> await \_trigger_next_phase(r.phase_hint, purpose_id, tenant_id)

**Testkriterium:** Test: WebSocket-Approval → idempotency_token wird geprüft, Doppel-Approval gibt OK zurück ohne Seiteneffekt.

**Aufwand:** 6h Implementierung + 4h Tests

------------------------------------------------------------------------

\#4: Feedback Re-Execution Loop verdrahten

**Dateien:** api/chat.py – Zeile 443 (REST), Zeile 909 (WebSocket); services/feedback_loop.py – redispatch_agent() Zeile 233

**Änderungen:**

- REST-Pfad (chat.py Zeile 443): Nach integrate_prd_feedback() den Aufruf redispatch_agent(task_id=primary_artifact.task_id, tenant_id=tenant_id) einfügen.

- WebSocket-Pfad (chat.py Zeile 909): Nach run_requirements_feedback() und Artifact-Speicherung den gleichen redispatch_agent()-Aufruf einfügen.

- Import hinzufügen: from services.feedback_loop import redispatch_agent

- Fehlerbehandlung: redispatch_agent() gibt bool zurück – bei False Fehlermeldung an Frontend senden.

**Code (Vorher/Nachher):**

> \# chat.py REST-Pfad (nach Zeile 443):
>
> agent_msg = integrate_prd_feedback(...)
>
> \# NEU:
>
> success = redispatch_agent(
>
> task_id=primary_artifact.task_id,
>
> tenant_id=tenant_id,
>
> )
>
> if not success:
>
> logger.error("Failed to redispatch agent for task %s", primary_artifact.task_id)
>
> \# chat.py WebSocket-Pfad (nach Zeile 935):
>
> \# NEU:
>
> success = redispatch_agent(
>
> task_id=target_task_id,
>
> tenant_id=tenant_id,
>
> )

**Testkriterium:** E2E-Test: Feedback auf PRD geben → Task-Status wechselt zu DOING → Agent wird mit Feedback-Kontext erneut ausgeführt → neues Artifact entsteht.

**Aufwand:** 4h Implementierung + 6h E2E-Tests

------------------------------------------------------------------------

\#13: Code Review Re-Review Loop automatisieren

**Dateien:** services/review_gate.py – dispatch_re_review() Zeile 268, check_fix_tasks_complete() Zeile 332; tasks/celery_app.py

**Änderungen:**

- In celery_app.py task_success Handler: Wenn der abgeschlossene Task ein Fix-Task ist (erkennbar an parent_task_id oder task.role == 'dev' mit is_fix_task Flag), prüfe ob alle Fix-Tasks für den zugehörigen Review-Task done sind.

- Verwende check_fix_tasks_complete(review_task_id) aus review_gate.py.

- Wenn True: Rufe dispatch_re_review(review_task_id, tenant_id) auf.

- Neues Feld in Task-Modell: review_parent_id (Optional\[str\]) – verweist auf den Review-Task, der den Fix ausgelöst hat.

**Code (Vorher/Nachher):**

> \# celery_app.py - Im task_success Handler:
>
> @task_success.connect
>
> def handle_task_success(sender=None, result=None, \*\*kwargs):
>
> \# ... existing logic ...
>
> \# NEU: Check if this was a fix task
>
> if task_obj.review_parent_id:
>
> from ai_org_backend.services.review_gate import (
>
> check_fix_tasks_complete, dispatch_re_review
>
> )
>
> if check_fix_tasks_complete(task_obj.review_parent_id):
>
> dispatch_re_review(
>
> review_task_id=task_obj.review_parent_id,
>
> tenant_id=task_obj.tenant_id,
>
> )

**Testkriterium:** Test: Fix-Task abschließen → wenn alle Fixes done, wird Re-Review automatisch dispatched.

**Aufwand:** 6h Implementierung + 4h Tests

------------------------------------------------------------------------

**Sprint 2 Acceptance Gate:** Ein einziger Approval-Pfad. Feedback führt zu Agent-Re-Execution. Review-Loop schließt sich.

5\. Sprint 3: Graph Integrity & Stuck-Task Recovery

**Ziel:** Kein Deadlock, kein Datendrift, keine Zombie-Tasks.

|  |  |  |  |
|----|----|----|----|
| **Fix** | **Titel** | **Aufwand** | **Abhängigkeit** |
| **\#6** | Graph Sync Retry mit Reconciliation | 8h Implementierung + 6h Tests | Keine |
| **\#7** | Cycle Detection in repo.link() | 4h Implementierung + 3h Tests | \#6 (Graph stabil) |
| **\#11** | Stuck-Task Watchdog implementieren | 4h Implementierung + 3h Tests | Keine |
| **\#3** | Race Condition: CAS-basierte Dispatch-Logik | 6h Implementierung + 6h Tests | \#6, \#11 |

\#6: Graph Sync Retry mit Reconciliation

**Dateien:** repo.py Zeile 49-65; services/graph_sync.py Zeile 24-91; tasks/graph_sync_task.py

**Änderungen:**

- graph_sync.py: Alle upsert\_\*()-Funktionen mit Retry-Dekorator wrappen (3 Versuche, exponential backoff 2s–2min, Jitter).

- repo.py Zeile 49-65: Nach SQL-Commit statt synchronem graph_sync-Aufruf einen Celery-Task graph.sync.deferred enqueuen.

- Neuer Celery-Beat-Job: reconcile_graph alle 10 Minuten – liest alle Tasks aus PostgreSQL, vergleicht mit Neo4j, korrigiert Abweichungen.

- Logging: Jede Abweichung wird als WARNING geloggt mit Task-ID und Feldname.

**Code (Vorher/Nachher):**

> \# graph_sync.py - Retry-Dekorator:
>
> from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
>
> from neo4j.exceptions import ServiceUnavailable, SessionExpired
>
> @retry(
>
> stop=stop_after_attempt(3),
>
> wait=wait_exponential(multiplier=2, min=2, max=120),
>
> retry=retry_if_exception_type((ServiceUnavailable, SessionExpired)),
>
> reraise=True,
>
> )
>
> def upsert_task(task_id, \*, desc=None, status=None, ...):
>
> \# existing logic
>
> \# repo.py - Deferred sync:
>
> s.commit()
>
> s.refresh(obj)
>
> from ai_org_backend.tasks.graph_sync_task import sync_task_deferred
>
> sync_task_deferred.delay(obj.id, obj.tenant_id)

**Testkriterium:** Test: Neo4j herunterfahren → Task-Update in SQL erfolgreich → Retry-Task in Queue → Neo4j wieder hoch → Sync erfolgt. Reconciliation-Job findet Abweichung und korrigiert.

**Aufwand:** 8h Implementierung + 6h Tests

------------------------------------------------------------------------

\#7: Cycle Detection in repo.link()

**Dateien:** repo.py Zeile 142-152; services/cycle_detector.py Zeile 87-95

**Änderungen:**

- repo.py Zeile 142: Vor dem Erstellen der TaskDependency alle existierenden Abhängigkeiten laden + die neue Kante als Graph aufbauen.

- Topologischen Sort durchführen (Kahn's Algorithm). Wenn Cycle: raise CyclicDependencyError.

- Alternativ: Neo4j-seitige Validierung mit Cypher-Query: MATCH path = (a)-\[:DEPENDS_ON\*\]-\>(b) WHERE a.id = to_id AND b.id = from_id RETURN path LIMIT 1.

- HTTP-Response bei Cycle: 409 Conflict mit Beschreibung des Zyklus.

**Code (Vorher/Nachher):**

> \# repo.py - link() NACHHER:
>
> def link(self, from_id: str, to_id: str, \*, kind: str = "FINISH_START") -\> None:
>
> \# NEU: Cycle-Check vor Persistierung
>
> with SessionLocal() as s:
>
> existing = s.exec(select(TaskDependency)).all()
>
> edges = \[(d.from_id, d.to_id) for d in existing\]
>
> edges.append((from_id, to_id))
>
> from ai_org_backend.services.cycle_detector import detect_cycles_from_edges
>
> cycles = detect_cycles_from_edges(edges)
>
> if cycles:
>
> raise CyclicDependencyError(cycles)
>
> s.add(TaskDependency(from_id=from_id, to_id=to_id, dependency_type=kind))
>
> s.commit()
>
> graph_sync.upsert_dependency(from_id, to_id, kind=kind)

**Testkriterium:** Test: link(A→B), link(B→C), link(C→A) → CyclicDependencyError bei drittem Aufruf.

**Aufwand:** 4h Implementierung + 3h Tests

------------------------------------------------------------------------

\#11: Stuck-Task Watchdog implementieren

**Dateien:** models/task.py Zeile 122; celeryconfig.py; Neuer Task: tasks/watchdog.py

**Änderungen:**

- Neuen Celery-Beat-Task erstellen: watchdog.detect_stuck_tasks, Intervall: 5 Minuten.

- Query: SELECT \* FROM task WHERE status = 'doing' AND last_heartbeat_at \< NOW() - INTERVAL '10 minutes'.

- Für jeden gefundenen Task: Status auf 'failed' setzen, Notes = 'Watchdog: No heartbeat for 10+ minutes'.

- Wenn task.retries \< 3: Status auf 'todo' (Retry). Wenn \>= 3: move_to_dlq().

- Alert: Sentry-Event oder Log-Alert bei jedem Watchdog-Fund.

**Code (Vorher/Nachher):**

> \# tasks/watchdog.py - NEU:
>
> from celery import shared_task
>
> from datetime import datetime, timedelta
>
> @shared_task(name="watchdog.detect_stuck_tasks")
>
> def detect_stuck_tasks():
>
> threshold = datetime.utcnow() - timedelta(minutes=10)
>
> with SessionLocal() as s:
>
> stuck = s.exec(
>
> select(Task)
>
> .where(Task.status == TaskStatus.DOING)
>
> .where(Task.last_heartbeat_at \< threshold)
>
> ).all()
>
> for task in stuck:
>
> if task.retries \< 3:
>
> task.status = TaskStatus.TODO
>
> task.retries += 1
>
> task.notes = f"Watchdog retry \#{task.retries}: stale heartbeat"
>
> log.warning("Watchdog: Retrying stuck task %s (attempt %d)", task.id, task.retries)
>
> else:
>
> move_to_dlq(task.id, "Watchdog: max retries after stuck detection")
>
> s.add(task)
>
> s.commit()
>
> \# celeryconfig.py - Beat Schedule hinzufügen:
>
> CELERY_BEAT_SCHEDULE\["watchdog-stuck-tasks"\] = {
>
> "task": "watchdog.detect_stuck_tasks",
>
> "schedule": 300.0, \# 5 Minuten
>
> }

**Testkriterium:** Test: Task in DOING setzen mit last_heartbeat_at = 15 Minuten in der Vergangenheit → Watchdog setzt auf TODO. Nach 3 Retries → DEAD_LETTER.

**Aufwand:** 4h Implementierung + 3h Tests

------------------------------------------------------------------------

\#3: Race Condition: CAS-basierte Dispatch-Logik

**Dateien:** orchestrator/scheduler.py Zeile 836-853; orchestrator/locks.py Zeile 111-124

**Änderungen:**

- locks.py: Lock-TTL von 60s auf 300s erhöhen (gleich wie Celery TASK_SOFT_TIME_LIMIT).

- Heartbeat-Renewal: Lock-Halter erneuert TTL alle 30s via Redis EXPIRE-Befehl.

- scheduler.py Zeile 838: Nach Lock-Erwerb: Compare-And-Swap auf Task-Status. Lese task.status erneut aus DB. Wenn != 'todo': Lock freigeben, skip.

- Neues Feld: task.dispatch_version (Integer). UPDATE task SET status='doing', dispatch_version=dispatch_version+1 WHERE id=? AND status='todo' AND dispatch_version=?. Wenn affected_rows == 0: Skip.

**Code (Vorher/Nachher):**

> \# scheduler.py - CAS-basierter Dispatch:
>
> dispatch_token = task_dispatch_lock(TENANT, task_id, ttl=300)
>
> if not dispatch_token:
>
> continue
>
> \# CAS: Atomisches Status-Update
>
> with SessionLocal() as s:
>
> result = s.exec(
>
> text("""
>
> UPDATE task
>
> SET status = 'doing', dispatch_version = dispatch_version + 1
>
> WHERE id = :tid AND status = 'todo' AND dispatch_version = :ver
>
> """),
>
> {"tid": task_id, "ver": current_version}
>
> )
>
> if result.rowcount == 0:
>
> release_lock(TENANT, task_id, dispatch_token)
>
> continue \# Another worker got there first
>
> s.commit()

**Testkriterium:** Lasttest: 3 Scheduler-Instanzen gleichzeitig → kein Task wird doppelt dispatched.

**Aufwand:** 6h Implementierung + 6h Tests

------------------------------------------------------------------------

**Sprint 3 Acceptance Gate:** Kein Deadlock, kein Datendrift, keine Zombie-Tasks.

6\. Sprint 4: Multi-Agent Conflict Prevention & Validation

**Ziel:** Generierter Code ist konfliktfrei und kompiliert.

|  |  |  |  |
|----|----|----|----|
| **Fix** | **Titel** | **Aufwand** | **Abhängigkeit** |
| **\#8** | File-Ownership Reservation System | 8h Implementierung + 4h Tests | \#7 (DAG valide) |
| **\#23** | Peer Context: Harte Constraints statt Advisory | 4h Implementierung + 3h Tests | \#8 (Reservierung) |
| **\#10** | Post-Assembly Build Validation | 6h Implementierung + 4h Tests | \#8 (kein Konflikt) |
| **\#25** | Planner JSON Schema verschärfen | 2h Implementierung + 2h Tests | Keine |

\#8: File-Ownership Reservation System

**Dateien:** Neuer Service: services/file_reservation.py; agents/agent_dev.py Zeile 83-92; services/conflict_detector.py

**Änderungen:**

- Neues Modell: FileReservation(task_id, file_path, purpose_id, created_at). Unique Constraint auf (file_path, purpose_id).

- Neuer Service: file_reservation.py mit claim_files(task_id, file_paths) und release_files(task_id).

- Planner-Output erweitern: Jeder Task bekommt ein 'target_files'-Array.

- agent_dev.py: Vor Code-Generierung claim_files() aufrufen. Wenn Konflikt: Task wartet oder wird umgeroutet.

- Nach Task-Abschluss: release_files() aufrufen.

**Code (Vorher/Nachher):**

> \# services/file_reservation.py - NEU:
>
> class FileReservation(SQLModel, table=True):
>
> id: str = Field(default_factory=lambda: str(uuid4()))
>
> task_id: str = Field(foreign_key="task.id")
>
> file_path: str
>
> purpose_id: str = Field(foreign_key="purpose.id")
>
> created_at: datetime = Field(default_factory=datetime.utcnow)
>
> \_\_table_args\_\_ = (UniqueConstraint("file_path", "purpose_id"),)
>
> def claim_files(task_id: str, file_paths: list\[str\], purpose_id: str) -\> bool:
>
> with SessionLocal() as s:
>
> for fp in file_paths:
>
> existing = s.exec(
>
> select(FileReservation)
>
> .where(FileReservation.file_path == fp, FileReservation.purpose_id == purpose_id)
>
> ).first()
>
> if existing and existing.task_id != task_id:
>
> return False \# Conflict
>
> s.add(FileReservation(task_id=task_id, file_path=fp, purpose_id=purpose_id))
>
> s.commit()
>
> return True

**Testkriterium:** Test: Dev1 claimed 'app.py'. Dev2 versucht claim 'app.py' → Abgelehnt. Dev1 released → Dev2 claim erfolgreich.

**Aufwand:** 8h Implementierung + 4h Tests

------------------------------------------------------------------------

\#23: Peer Context: Harte Constraints statt Advisory

**Dateien:** services/peer_context.py Zeile 92-185; agents/agent_dev.py Zeile 113, 160

**Änderungen:**

- peer_context.py: get_peer_context() um claimed_files erweitern – aus FileReservation-Tabelle lesen.

- Prompt-Injection verschärfen: Statt 'avoid conflicts' explizit: 'Du DARFST NICHT in folgende Dateien schreiben: \[Liste\]. Wenn du eine dieser Dateien ändern musst, erstelle stattdessen eine neue Datei mit dem Suffix \_\<task_id\>.'

- Post-Generation-Check: Nach LLM-Response prüfen, ob generierte Dateien in der claimed_files-Liste eines anderen Tasks sind.

**Code (Vorher/Nachher):**

> \# peer_context.py - Erweitert:
>
> def get_peer_context(purpose_id, \*, exclude_task_id=None):
>
> ctx = PeerContext(...)
>
> \# NEU: Geladene Reservierungen
>
> reservations = session.exec(
>
> select(FileReservation)
>
> .where(FileReservation.purpose_id == purpose_id)
>
> .where(FileReservation.task_id != exclude_task_id)
>
> ).all()
>
> ctx.forbidden_files = \[r.file_path for r in reservations\]
>
> return ctx
>
> \# PeerContext.to_prompt_text() erweitern:
>
> def to_prompt_text(self):
>
> text = self.\_existing_text()
>
> if self.forbidden_files:
>
> text += "\n\nFORBIDDEN FILES (do NOT write to these):\n"
>
> for f in self.forbidden_files:
>
> text += f"- {f}\n"
>
> return text

**Testkriterium:** Test: Dev-Agent erhält forbidden_files im Prompt. Generierter Code enthält keine der verbotenen Dateien.

**Aufwand:** 4h Implementierung + 3h Tests

------------------------------------------------------------------------

\#10: Post-Assembly Build Validation

**Dateien:** agents/repo_composer.py Zeile 99-108; Neuer Service: services/build_validator.py

**Änderungen:**

- Neuen Service build_validator.py erstellen mit validate_repository(workspace_path) → ValidationReport.

- Python-Dateien: py_compile.compile() für jede .py-Datei.

- JS/TS-Dateien: Syntax-Check via esprima/acorn oder einfach node --check.

- requirements.txt: Prüfe ob alle importierten Packages gelistet sind.

- package.json: Prüfe ob Datei valides JSON ist.

- In repo_composer.py nach Zeile 108: validate_repository() aufrufen. Bei kritischen Fehlern: Task auf FAILED setzen, Fehlerbericht als Artifact anhängen.

**Code (Vorher/Nachher):**

> \# services/build_validator.py - NEU:
>
> import py_compile, json, subprocess
>
> @dataclass
>
> class ValidationReport:
>
> errors: list\[str\]
>
> warnings: list\[str\]
>
> is_valid: bool
>
> def validate_repository(workspace_path: str) -\> ValidationReport:
>
> errors, warnings = \[\], \[\]
>
> for py_file in Path(workspace_path).rglob("\*.py"):
>
> try:
>
> py_compile.compile(str(py_file), doraise=True)
>
> except py_compile.PyCompileError as e:
>
> errors.append(f"Syntax error in {py_file.name}: {e}")
>
> for json_file in Path(workspace_path).rglob("\*.json"):
>
> try:
>
> json.loads(json_file.read_text())
>
> except json.JSONDecodeError as e:
>
> errors.append(f"Invalid JSON in {json_file.name}: {e}")
>
> return ValidationReport(errors=errors, warnings=warnings, is_valid=len(errors)==0)

**Testkriterium:** Test: Generiertes Repo mit Syntax-Fehler in main.py → ValidationReport.is_valid == False. Task bleibt auf FAILED.

**Aufwand:** 6h Implementierung + 4h Tests

------------------------------------------------------------------------

\#25: Planner JSON Schema verschärfen

**Dateien:** agents/planner.py Zeile 70-107, 224-231

**Änderungen:**

- Zeile 75-106: additionalProperties auf false setzen in jedem Object-Schema.

- Zeile 225 (Error Note bei Retry): Schema in die error_note aufnehmen, damit der LLM beim Retry das exakte erwartete Format kennt.

- Zeile 232: Beim Model-Upgrade (o3 → o3-pro) auch temperature auf 0.1 senken für deterministischere Outputs.

**Code (Vorher/Nachher):**

> \# planner.py - Schema korrigieren:
>
> TASKS_SCHEMA = {
>
> "type": "array",
>
> "minItems": 1,
>
> "maxItems": 200,
>
> "items": {
>
> "type": "object",
>
> "additionalProperties": False, \# WAR: True
>
> "required": \["id", "description", "depends_on", ...\],
>
> ...
>
> }
>
> }
>
> \# Retry error_note erweitern (Zeile 225):
>
> error_note = (
>
> f"Previous attempt failed: {str(e)}\n"
>
> f"Expected JSON schema: {json.dumps(TASKS_SCHEMA, indent=2)}"
>
> )

**Testkriterium:** Test: LLM-Output mit zusätzlichem Feld 'foo' → jsonschema.ValidationError. Retry-Prompt enthält Schema.

**Aufwand:** 2h Implementierung + 2h Tests

------------------------------------------------------------------------

**Sprint 4 Acceptance Gate:** Generierter Code ist konfliktfrei und kompiliert.

7\. Sprint 5: LLM Resilience & Data Flow Hardening

**Ziel:** Keine Silent Failures. Transiente Fehler werden automatisch abgefangen.

|  |  |  |  |
|----|----|----|----|
| **Fix** | **Titel** | **Aufwand** | **Abhängigkeit** |
| **\#14** | Double Budget Debit eliminieren | 3h Implementierung + 2h Tests | Keine |
| **\#15** | Alle Agents auf resilient_llm_call() umstellen | 4h Implementierung + 4h Tests | Keine |
| **\#16** | Explizite LLM Call Timeouts | 3h Implementierung + 2h Tests | \#15 |
| **\#17** | Jinja2 Template Variable Validation | 3h Implementierung + 2h Tests | Keine |
| **\#18** | Truncation Warnings statt Silent Cutoff | 2h Implementierung + 1h Tests | Keine |
| **\#19** | Zentraler Model Selector | 3h Implementierung + 2h Tests | \#15 (Retry-Integration) |

\#14: Double Budget Debit eliminieren

**Dateien:** orchestrator/scheduler.py Zeile 318 und Zeile 896

**Änderungen:**

- Zeile 896: Budget-Debit im Hauptloop ENTFERNEN.

- Zeile 318 in \_dispatch_task() bleibt als einziger Debit-Punkt.

- Neuer atomarer check_and_debit(): SELECT budget_remaining FROM purpose WHERE id=? FOR UPDATE → UPDATE SET budget_remaining = budget_remaining - cost WHERE budget_remaining \>= cost. Wenn affected_rows == 0: BudgetExhaustedError.

**Code (Vorher/Nachher):**

> \# services/budget.py - Atomarer Debit:
>
> def check_and_debit(purpose_id: str, cost: float, \*, session: Session) -\> bool:
>
> result = session.exec(text("""
>
> UPDATE purpose
>
> SET budget_remaining = budget_remaining - :cost
>
> WHERE id = :pid AND budget_remaining \>= :cost
>
> """), {"pid": purpose_id, "cost": cost})
>
> return result.rowcount \> 0

**Testkriterium:** Test: Budget = 10, zwei parallele Debits à 8 → nur einer erfolgreich.

**Aufwand:** 3h Implementierung + 2h Tests

------------------------------------------------------------------------

\#15: Alle Agents auf resilient_llm_call() umstellen

**Dateien:** services/llm_client.py Zeile 196-269; agents/architect.py, planner.py, agent_dev.py, vision.py, product_owner.py, reviewer.py, repo_composer.py

**Änderungen:**

- In jedem Agent: Direkten chat_with_tools()-Aufruf durch resilient_llm_call() ersetzen.

- resilient_llm_call() hat bereits: exponential backoff, model escalation, retry.

- Konfiguration pro Agent: max_retries=3, backoff_base=2, fallback_model=next_tier.

- Logging: Jeder Retry wird als WARNING geloggt mit Fehlergrund.

**Code (Vorher/Nachher):**

> \# Beispiel agent_dev.py - VORHER:
>
> response = chat_with_tools(messages, tools=tools, model=model)
>
> \# NACHHER:
>
> response = resilient_llm_call(
>
> call_fn=chat_with_tools,
>
> messages=messages,
>
> tools=tools,
>
> model=model,
>
> fallback_models=\["gpt-4o", "gpt-4o-mini"\],
>
> max_retries=3,
>
> usage_label="dev_agent",
>
> )

**Testkriterium:** Test: Mock LLM mit 2x RateLimitError, dann Erfolg → Agent liefert Ergebnis nach 2 Retries.

**Aufwand:** 4h Implementierung + 4h Tests

------------------------------------------------------------------------

\#16: Explizite LLM Call Timeouts

**Dateien:** services/llm_client.py Zeile 304-312

**Änderungen:**

- chat_with_tools() Signatur: timeout: int = 300 als Parameter hinzufügen.

- Für OpenAI-Client: client.chat.completions.create(..., timeout=timeout).

- Für Anthropic-Client: client.messages.create(..., timeout=timeout).

- Reasoning-Modelle (o3, o3-pro): timeout = 900 als Default.

- TimeoutError abfangen und als retriable Exception behandeln.

**Code (Vorher/Nachher):**

> \# llm_client.py - NACHHER:
>
> def chat_with_tools(
>
> messages, tools=None, model=None, temperature=0.2,
>
> max_output_tokens=None, tenant_id=None, usage_label="generic",
>
> timeout: int = 300, \# NEU
>
> ) -\> Dict\[str, Any\]:
>
> if model in ("o3", "o3-pro"):
>
> timeout = max(timeout, 900) \# Reasoning models need more time
>
> \# ... pass timeout to client calls

**Testkriterium:** Test: Mock-LLM mit 10s Delay, timeout=5 → TimeoutError. timeout=30 → Erfolg.

**Aufwand:** 3h Implementierung + 2h Tests

------------------------------------------------------------------------

\#17: Jinja2 Template Variable Validation

**Dateien:** agents/utils.py Zeile 77-100

**Änderungen:**

- Neue Funktion validate_template_context(template, context: dict) in utils.py.

- Jinja2 Environment.parse() gibt AST, daraus undeclared_variables extrahieren.

- Fehlende Variablen: TemplateContextError mit Liste der fehlenden Variablen.

- Aufruf vor jedem template.render() in allen Agents.

**Code (Vorher/Nachher):**

> \# utils.py - NEU:
>
> from jinja2 import meta as jinja2_meta
>
> def validate_template_context(template, context: dict) -\> None:
>
> env = template.environment
>
> ast = env.parse(template.source)
>
> required = jinja2_meta.find_undeclared_variables(ast)
>
> missing = required - set(context.keys())
>
> if missing:
>
> raise TemplateContextError(
>
> f"Missing template variables: {', '.join(sorted(missing))}"
>
> )
>
> def render_validated(template, context: dict) -\> str:
>
> validate_template_context(template, context)
>
> return template.render(\*\*context)

**Testkriterium:** Test: Template mit {{ vision_doc }} aber context ohne vision_doc → TemplateContextError.

**Aufwand:** 3h Implementierung + 2h Tests

------------------------------------------------------------------------

\#18: Truncation Warnings statt Silent Cutoff

**Dateien:** services/cumulative_context.py Zeile 113-114

**Änderungen:**

- Zeile 113: Vor Truncation: log.warning() mit Phase-Name, Original-Länge, max_chars_per_phase.

- Truncation-Marker erweitern: '\[... truncated from {original_len} to {max_chars_per_phase} chars ...\]'

- Rückgabe-Objekt um truncated_phases: list\[str\] erweitern.

- Langfristig: Summarization statt Hard-Truncation (LLM-basierte Zusammenfassung).

**Code (Vorher/Nachher):**

> \# cumulative_context.py - NACHHER:
>
> if len(text) \> max_chars_per_phase:
>
> log.warning(
>
> "Truncating phase '%s' context from %d to %d chars for purpose %s",
>
> phase_name, len(text), max_chars_per_phase, purpose_id
>
> )
>
> text = text\[:max_chars_per_phase\] + (
>
> f"\n\n\[... truncated from {len(text)} to {max_chars_per_phase} chars ...\]"
>
> )
>
> truncated_phases.append(phase_name)

**Testkriterium:** Test: Artifact mit 100k Zeichen → Warning im Log, truncated_phases enthält Phase-Name.

**Aufwand:** 2h Implementierung + 1h Tests

------------------------------------------------------------------------

\#19: Zentraler Model Selector

**Dateien:** agents/architect.py Zeile 26; agents/planner.py; agents/agent_dev.py Zeile 164; Neuer Service: services/model_selector.py

**Änderungen:**

- Neuen Service model_selector.py erstellen: get_model(agent_role: str, purpose_id: str, tier: str = 'default') → str.

- Konfiguration in DB oder Config-Datei: Mapping von (role, tier) → model_name.

- Default-Tiers: 'default' (erste Wahl), 'fallback' (bei Retry), 'economy' (bei Budget-Knappheit).

- In allen Agents: Hardcoded Model-Strings durch get_model() ersetzen.

**Code (Vorher/Nachher):**

> \# services/model_selector.py - NEU:
>
> MODEL_CONFIG = {
>
> "architect": {"default": "o3", "fallback": "gpt-4o", "economy": "gpt-4o-mini"},
>
> "planner": {"default": "o3", "fallback": "o3-pro", "economy": "gpt-4o"},
>
> "dev": {"default": "gpt-4o", "fallback": "gpt-4o-mini", "economy": "gpt-4o-mini"},
>
> "vision": {"default": "gpt-4o", "fallback": "gpt-4o-mini", "economy": "gpt-4o-mini"},
>
> \# ...
>
> }
>
> def get_model(role: str, tier: str = "default") -\> str:
>
> return MODEL_CONFIG.get(role, {}).get(tier, "gpt-4o")

**Testkriterium:** Test: get_model('architect') == 'o3'. get_model('architect', 'fallback') == 'gpt-4o'.

**Aufwand:** 3h Implementierung + 2h Tests

------------------------------------------------------------------------

**Sprint 5 Acceptance Gate:** Keine Silent Failures. Transiente Fehler werden automatisch abgefangen.

8\. Sprint 6: DB Migrations, Frontend & Observability

**Ziel:** Saubere DB, Echtzeit-UI, produktionsreifer Auto-Modus.

|  |  |  |  |
|----|----|----|----|
| **Fix** | **Titel** | **Aufwand** | **Abhängigkeit** |
| **\#20** | Migration Chain konsolidieren | 6h Implementierung + 4h Tests | Keine |
| **\#21** | Phase Slug Validation API | 3h Implementierung + 2h Tests | \#20 (Schema stabil) |
| **\#22** | Auto-Mode Backend Trigger implementieren | 6h Implementierung + 4h E2E-Tests | \#1, \#5 (Gates + Approval) |
| **\#24** | Echtzeit-Status via Server-Sent Events | 8h Implementierung + 6h Tests | \#21 (API stabil) |

\#20: Migration Chain konsolidieren

**Dateien:** migrations/versions/; backend/ai_org_backend/alembic/versions/; alembic.ini

**Änderungen:**

- Legacy-Verzeichnis migrations/versions/ archivieren (nicht löschen, nur README hinzufügen).

- Kanonisches Verzeichnis: backend/ai_org_backend/alembic/versions/.

- Revision-ID-Mismatches fixen: down_revision muss EXAKT der revision des Vorgängers entsprechen.

- Konkret: s2-Migration down_revision von 's1_cascade_constraints' auf '20260329_s1_cascade_and_constraints' ändern.

- CI-Check hinzufügen: alembic branches muss leer sein. alembic upgrade head auf leerer DB muss durchlaufen.

- Fehlende mode-Column in kanonische Migrations aufnehmen.

**Code (Vorher/Nachher):**

> \# alembic/versions/20260329_s2_version_and_heartbeat.py - FIX:
>
> revision = "s2_03_version_heartbeat"
>
> down_revision = "20260329_s1_cascade_and_constraints" \# EXAKTER Match
>
> \# CI Pipeline (.github/workflows/test.yml):
>
> \- name: Validate migrations
>
> run: \|
>
> alembic upgrade head
>
> alembic downgrade base
>
> alembic upgrade head
>
> test -z "\$(alembic branches)"

**Testkriterium:** Test: alembic upgrade head auf leerer DB → kein Fehler. alembic branches → leere Ausgabe.

**Aufwand:** 6h Implementierung + 4h Tests

------------------------------------------------------------------------

\#21: Phase Slug Validation API

**Dateien:** api/pipeline.py; frontend phaseConfig.ts

**Änderungen:**

- Neuer Endpoint: GET /api/pipeline/phases → gibt kanonische Phase-Slug-Liste zurück.

- Frontend: phaseConfig.ts beim App-Start gegen diesen Endpoint validieren.

- Warnung im Frontend, wenn ein Backend-Slug nicht in phaseConfig.ts gemappt ist.

- Langfristig: phaseConfig.ts generieren aus Backend-Endpoint (Single Source of Truth).

**Code (Vorher/Nachher):**

> \# api/pipeline.py - NEU:
>
> @router.get("/pipeline/phases")
>
> def list_pipeline_phases(current_tenant: Tenant = Depends(get_current_tenant)):
>
> with SessionLocal() as s:
>
> phases = s.exec(
>
> select(PipelinePhase)
>
> .where(PipelinePhase.tenant_id == current_tenant.id)
>
> .order_by(PipelinePhase.position)
>
> ).all()
>
> return \[{"slug": p.slug, "name": p.name, "position": p.position} for p in phases\]

**Testkriterium:** Test: GET /api/pipeline/phases gibt alle Phasen in richtiger Reihenfolge zurück.

**Aufwand:** 3h Implementierung + 2h Tests

------------------------------------------------------------------------

\#22: Auto-Mode Backend Trigger implementieren

**Dateien:** api/purposes.py Zeile 71-89; Neuer Task: tasks/auto_mode.py

**Änderungen:**

- api/purposes.py: Nach mode='auto' setzen → Celery-Task auto_mode.activate.delay(purpose_id, tenant_id) enqueuen.

- Neuer Task auto_mode.activate: Für jede Phase mit approval-Gate prüfen, ob Artifact vorhanden und auto-approved werden kann.

- Wenn ja: approve_artifact() aufrufen und nächste Phase triggern.

- Wenn nein: Warten (der normale Scheduler übernimmt).

**Code (Vorher/Nachher):**

> \# tasks/auto_mode.py - NEU:
>
> @shared_task(name="auto_mode.activate")
>
> def activate_auto_mode(purpose_id: str, tenant_id: str):
>
> with SessionLocal() as s:
>
> purpose = s.get(Purpose, purpose_id)
>
> if not purpose or purpose.mode != "auto":
>
> return
>
> \# Find all pending approval gates and auto-approve
>
> pending = s.exec(
>
> select(Task)
>
> .where(Task.purpose_id == purpose_id, Task.status == TaskStatus.DONE)
>
> .where(Task.requires_approval == True)
>
> ).all()
>
> for task in pending:
>
> artifact = \_latest_artifact(task.id, s)
>
> if artifact and not artifact.released:
>
> approve_artifact(artifact.id, tenant_id=tenant_id, purpose_id=purpose_id)
>
> \# api/purposes.py - Zeile 85 erweitern:
>
> purpose.mode = new_mode
>
> if new_mode == "auto":
>
> from ai_org_backend.tasks.auto_mode import activate_auto_mode
>
> activate_auto_mode.delay(purpose.id, current_tenant.id)

**Testkriterium:** E2E-Test: Mode auf 'auto' setzen → alle pending Approvals werden automatisch erteilt → Pipeline läuft weiter.

**Aufwand:** 6h Implementierung + 4h E2E-Tests

------------------------------------------------------------------------

\#24: Echtzeit-Status via Server-Sent Events

**Dateien:** Neuer Endpoint: api/events.py; Frontend: pipelineStore.ts Zeile 149

**Änderungen:**

- Neuer SSE-Endpoint: GET /api/purposes/{purpose_id}/events → text/event-stream.

- Backend: Redis Pub/Sub Kanal pro Purpose. Scheduler und Celery-Callbacks publishen Statusänderungen.

- Event-Typen: task_status_changed, phase_completed, artifact_created, approval_required.

- Frontend: EventSource statt Polling. Fallback auf 6s-Polling wenn SSE nicht verfügbar.

- Admin-Dashboard: Polling-Intervall durch SSE ersetzen.

**Code (Vorher/Nachher):**

> \# api/events.py - NEU:
>
> from fastapi.responses import StreamingResponse
>
> import asyncio, json
>
> @router.get("/purposes/{purpose_id}/events")
>
> async def purpose_events(purpose_id: str, current_tenant = Depends(get_current_tenant)):
>
> async def event_stream():
>
> pubsub = redis_pool.pubsub()
>
> pubsub.subscribe(f"events:{current_tenant.id}:{purpose_id}")
>
> try:
>
> while True:
>
> msg = pubsub.get_message(timeout=30)
>
> if msg and msg\["type"\] == "message":
>
> yield f"data: {msg\['data'\]}\n\n"
>
> else:
>
> yield f": keepalive\n\n" \# Prevent timeout
>
> finally:
>
> pubsub.unsubscribe()
>
> return StreamingResponse(event_stream(), media_type="text/event-stream")
>
> \# Frontend - pipelineStore.ts:
>
> const evtSource = new EventSource(\`/api/purposes/\${purposeId}/events\`);
>
> evtSource.onmessage = (e) =\> {
>
> const event = JSON.parse(e.data);
>
> updateTaskStatus(event.task_id, event.status);
>
> };

**Testkriterium:** Test: Task-Status ändern → SSE-Event wird innerhalb von 500ms empfangen.

**Aufwand:** 8h Implementierung + 6h Tests

------------------------------------------------------------------------

**Sprint 6 Acceptance Gate:** Saubere DB, Echtzeit-UI, produktionsreifer Auto-Modus.

9\. Gesamtaufwand & Meilensteine

|  |  |  |  |
|----|----|----|----|
| **Sprint** | **Fokus** | **Aufwand (Impl.)** | **Aufwand (Tests)** |
| **S1** | Phase-Gate & Artifact Validation | 12h | 11h |
| **S2** | Approval & Feedback Re-Execution | 16h | 14h |
| **S3** | Graph Integrity & Stuck-Task Recovery | 22h | 18h |
| **S4** | Multi-Agent Conflict Prevention | 20h | 13h |
| **S5** | LLM Resilience & Data Flow | 18h | 13h |
| **S6** | DB, Frontend & Observability | 23h | 16h |
| **GESAMT** | **Alle 25 Findings** | **~111h** | **~85h** |

**Gesamtaufwand: ~196 Personenstunden** (ca. 25 Personentage, verteilt auf 12 Wochen / 6 Sprints).

Nach Abschluss aller 6 Sprints ist die Pipeline in der Lage, ein Softwareprojekt vollautomatisch von der Purpose-Eingabe bis zum validierten, konfliktfreien ZIP-Export zu generieren – ohne menschliches Eingreifen, mit Echtzeit-Statusanzeige und robuster Fehlerbehandlung.
