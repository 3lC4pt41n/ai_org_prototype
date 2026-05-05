# Phase 0 Glossary

Einheitliche Begriffe für die folgenden Phasen.

| Begriff | Definition | Datenstruktur-Referenz | Lebenszyklus | Negativbeispiele |
| --- | --- | --- | --- | --- |
| Task | Kleinste ausführbare Arbeitseinheit der heutigen Runtime. | `backend/ai_org_backend/models/task.py::Task` | todo -> doing -> done/failed/skipped/budget_exceeded/dead_letter. | Kein Intent, kein Graph-Knotenvertrag und kein Artefakt. |
| Pipeline | Geordneter Ablauf zur Erzeugung oder Überarbeitung eines Purpose-Ergebnisses. | `models/pipeline.py::PipelineTemplate`, künftig `graph/schema.py::PipelineGraph` | Template-Auswahl -> Task-Erzeugung -> Worker-Ausführung -> Review/Release. | Keine einzelne Queue und keine lose Task-Liste ohne Abhängigkeiten. |
| Phase | Legacy-Schritt innerhalb eines Pipeline-Templates. | `models/pipeline.py::PipelinePhase` | Template-Definition -> Task-Instanz pro Purpose -> Abschluss oder Rework. | Kein frei synthetisierter Graph-Knoten und keine Runtime-Engine. |
| Purpose | Tenant-gebundener Zielkontext, unter dem Tasks, Artefakte und Chat-Kontext gruppiert werden. | `backend/ai_org_backend/models/purpose.py::Purpose` | Anlegen -> aktivieren/starten -> pausieren/fortführen -> löschen. | Kein einzelner Nutzerprompt und keine Agentenrolle. |
| Artifact | Persistiertes Ergebnis eines Tasks inklusive Versionierungs- und Feedback-Kontext. | `backend/ai_org_backend/models/artifact.py::Artifact` | Erzeugen -> referenzieren/reviewen -> versionieren -> freigeben oder invalidieren. | Kein Task-Status und kein flüchtiger Prompt. |
| Run | Konkrete Ausführung eines Graphen oder Legacy-Pipeline-Ablaufs. | Heute implizit über Task-Status/Heartbeat; künftig `runs` in Phase 2. | Start -> Node/Task-Ausführung -> Retry/Rework -> terminaler Status. | Kein Template und keine statische Architekturdefinition. |
| Node | Expliziter, typisierter Ausführungspunkt im künftigen `PipelineGraph`. | Künftig `backend/ai_org_backend/graph/schema.py::PipelineNode` | Validierung -> Scheduling -> Ausführung -> Output/Trace -> ggf. Rework. | Keine Legacy-Phase ohne Capability- und Schema-Vertrag. |
| Edge | Explizite Abhängigkeits- oder Feedback-Beziehung zwischen Graph-Knoten. | Heute `TaskDependency`; künftig `graph/schema.py::PipelineEdge` | Definition -> Validierung -> Aktivierung nach Bedingung -> Lineage/Invalidierung. | Keine Reihenfolgenummer und kein informeller Textverweis. |
