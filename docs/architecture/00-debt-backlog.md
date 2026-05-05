# Phase 0 Debt Backlog

Maximal 25 Einträge. Klassifikation: `blocking`, `important`, `nice-to-have`.

| Priorität | Schuld | Betroffene Stellen | Akzeptanz / Maßnahme |
| --- | --- | --- | --- |
| blocking | Intent-Semantik ist implizit an Rollen und Agent-Queues gekoppelt. | `backend/ai_org_backend/orchestrator/role_rules.py`, `tasks/celery_app.py` | Für Phase 1 akzeptiert: bestehendes Role-Routing bleibt Legacy-Adapter, bis `intent/` eingeführt ist. |
| blocking | Pipeline-Struktur ist als lineare Phase/Predecessor-Abfolge modelliert. | `backend/ai_org_backend/models/pipeline.py`, `services/pipeline_templates.py` | Für Phase 2 akzeptiert: Legacy-Phasen werden per Adapter nach `PipelineGraph` v2 migriert. |
| blocking | Rework ist in Feedback-/Review-Services verteilt und nicht als bounded Loop vertraglich modelliert. | `backend/ai_org_backend/services/feedback_loop.py`, `services/review_gate.py` | Für Phase 4 akzeptiert: Konsolidierung in `services/rework.py` mit `RevisionLimitPolicy`. |
| blocking | Graph- und Artefakt-Lineage liegen in mehreren Speichern ohne gemeinsamen Run-Trace. | `services/graph_sync.py`, `services/storage.py`, `models/artifact.py` | Für Phase 5 akzeptiert: OTel/OpenLineage wird als Korrelationsschicht ergänzt. |
| important | FastAPI und Celery importieren Runtime-Komponenten teilweise gegenseitig. | `main.py`, `tasks/celery_app.py` | Bei Engine-Abstraktion zyklische Imports reduzieren. |
| important | Task-Statuswerte sind Strings, obwohl ein Enum existiert. | `models/task.py` | Bei Graph-v2-Migration Statusübergänge zentralisieren. |
| important | Budget-Gates basieren auf geplanter Tokenzahl statt knotengenauer Kostenbudgets. | `tasks/celery_app.py`, `services/budget.py` | In Phase 2/5 auf Node-Budget und Cost-Trace erweitern. |
| important | Neo4j-Sync ist best effort und nicht vollständig replaybar. | `repo.py`, `services/graph_sync.py` | Für Phase 5 Run-Trace und Reconciliation dokumentieren. |
| important | Review-Fix-Logik erkennt Rework über Textpräfixe. | `tasks/celery_app.py`, `services/review_gate.py` | In Phase 4 durch explizite Edge-/Loop-Semantik ersetzen. |
| important | Template-Verträge sind Python-Objekte, nicht deklarative YAML-Artefakte. | `services/pipeline_templates.py` | In Phase 3 in Template-Bibliothek überführen. |
| nice-to-have | Mehrere Agentenmodule haben ähnliche Fehlerbehandlungs- und Repo-Update-Muster. | `backend/ai_org_backend/agents/*.py` | Nach stabilen Graph-Verträgen in gemeinsame Worker-Helfer extrahieren. |
| nice-to-have | Einige Verantwortungen sind nur durch Sprint-Kommentare dokumentiert. | `backend/tests/test_sprint*_audit.py` | Nach ADR-Updates historische Sprint-Kommentare reduzieren. |

## Blocking-Akzeptanz

Die ersten vier Einträge sind für diesen Sprint dokumentiert akzeptiert. Sie blockieren spätere Phasen fachlich, verhindern aber Phase 0 nicht, weil jeweils eine konkrete Zielphase und Migrationsrichtung festgelegt ist.
