# Phase 0 Audit Report

Quelle: `scripts/generate_architecture_audit.py`. Der Report wird aus Dateisystem- und AST-Scans erzeugt, nicht aus README-Text.

## Kurzbefund

- FastAPI-Routen: 57
- Celery-Tasks: 26
- Service-Module: 34
- Repository-Adapter: 3
- Datenmodell-Dateien: 13
- Python-Module insgesamt: 135

## FastAPI-Routen

| Methode | Pfad | Handler | Verantwortung |
| --- | --- | --- | --- |
| GET | `/` | `backend.ai_org_backend.api.root.root` | Public health endpoint with budget info for default tenant. |
| GET | `/api/` | `backend.ai_org_backend.api.root.api_index` | Health/Index endpoint for the API prefix. |
| GET | `/api/agent/{queue}/ping` | `backend.ai_org_backend.api.agents.ping` | ping endpoint. |
| GET | `/api/artifact/{artifact_id}` | `backend.ai_org_backend.api.pipeline.download_artifact` | Download the content of an artifact file by ID. |
| GET | `/api/artifact/{artifact_id}/meta` | `backend.ai_org_backend.api.artifact_bridge.get_artifact_by_id` | Return the stored metadata of an artifact (not the file content). |
| GET | `/api/artifacts` | `backend.ai_org_backend.api.pipeline.list_artifacts` | List all artifacts with related task info. |
| POST | `/api/artifacts/{artifact_id}/approve` | `backend.ai_org_backend.api.pipeline.approve_artifact` | approve artifact endpoint. |
| GET | `/api/artifacts/{artifact_id}/feedback` | `backend.ai_org_backend.api.artifact_bridge.get_feedback_for_artifact` | Return chat messages linked to an artifact via the join table. |
| GET | `/api/artifacts/{artifact_id}/feedback` | `backend.ai_org_backend.api.pipeline.get_artifact_feedback` | Return all feedback entries for an artifact, sorted by version ascending. |
| POST | `/api/artifacts/{artifact_id}/feedback` | `backend.ai_org_backend.api.artifact_bridge.post_feedback_for_artifact` | Store a feedback chat message and link it to the artifact. |
| POST | `/api/artifacts/{artifact_id}/feedback` | `backend.ai_org_backend.api.pipeline.post_artifact_feedback` | Store feedback for an artifact. |
| GET | `/api/artifacts/{artifact_id}/meta` | `backend.ai_org_backend.api.artifact_bridge.get_artifact_by_id` | Return the stored metadata of an artifact (not the file content). |
| GET | `/api/backlog` | `backend.ai_org_backend.api.pipeline.backlog` | backlog endpoint. |
| GET | `/api/chat/messages` | `backend.ai_org_backend.api.chat.get_chat_messages` | Retrieve chat messages for a given purpose with optional filtering. |
| POST | `/api/chat/messages` | `backend.ai_org_backend.api.chat.post_chat` | Send a message in the chat and get a response. |
| PATCH | `/api/chat/messages/{message_id}/tags` | `backend.ai_org_backend.api.chat.update_message_tags` | Update artifact tags for a chat message. |
| GET | `/api/context` | `backend.ai_org_backend.api.pipeline.get_context` | Get semantically relevant snippets for a given task. |
| GET | `/api/graph` | `backend.ai_org_backend.api.pipeline.get_graph` | Get all tasks and dependencies as graph data. |
| POST | `/api/login` | `backend.ai_org_backend.api.auth.login` | login endpoint. |
| GET | `/api/pause` | `backend.ai_org_backend.api.pipeline.get_pause_status` | get pause status endpoint. |
| POST | `/api/pause` | `backend.ai_org_backend.api.pipeline.pause_pipeline` | pause pipeline endpoint. |
| GET | `/api/pipeline/phases` | `backend.ai_org_backend.api.pipeline.list_pipeline_phases` | S6-#10.1: Return phase configuration for a purpose. |
| PUT | `/api/pipeline/phases/{phase_id}` | `backend.ai_org_backend.api.pipeline.update_pipeline_phase_endpoint` | update pipeline phase endpoint endpoint. |
| GET | `/api/pipeline/prompts` | `backend.ai_org_backend.api.pipeline.list_prompt_templates_endpoint` | list prompt templates endpoint endpoint. |
| POST | `/api/pipeline/prompts/assign` | `backend.ai_org_backend.api.pipeline.assign_prompt_template` | assign prompt template endpoint. |
| POST | `/api/pipeline/prompts/create` | `backend.ai_org_backend.api.pipeline.create_prompt_template` | create prompt template endpoint. |
| PUT | `/api/pipeline/prompts/update/{template_id}` | `backend.ai_org_backend.api.pipeline.update_prompt_template` | update prompt template endpoint. |
| GET | `/api/pipeline/templates` | `backend.ai_org_backend.api.pipeline.list_pipeline_templates_endpoint` | list pipeline templates endpoint endpoint. |
| GET | `/api/project.zip` | `backend.ai_org_backend.api.pipeline.download_project_archive` | Download a ZIP archive containing all artifacts for the tenant. |
| GET | `/api/purposes` | `backend.ai_org_backend.api.pipeline.list_purposes` | list purposes endpoint. |
| POST | `/api/purposes` | `backend.ai_org_backend.api.pipeline.create_purpose` | Create a new purpose and seed initial tasks via LLM agents. |
| DELETE | `/api/purposes/{purpose_id}` | `backend.ai_org_backend.api.purposes.delete_purpose` | Delete a Purpose and all related records. |
| PATCH | `/api/purposes/{purpose_id}` | `backend.ai_org_backend.api.purposes.update_purpose` | Update a Purpose (toggle mode auto/manual). |
| POST | `/api/purposes/{purpose_id}/activate` | `backend.ai_org_backend.api.purposes.activate_purpose` | activate purpose endpoint. |
| GET | `/api/purposes/{purpose_id}/graph` | `backend.ai_org_backend.api.pipeline.get_purpose_graph` | get purpose graph endpoint. |
| POST | `/api/purposes/{purpose_id}/pause` | `backend.ai_org_backend.api.purposes.pause_purpose` | pause purpose endpoint. |
| GET | `/api/purposes/{purpose_id}/pipeline` | `backend.ai_org_backend.api.pipeline.get_purpose_pipeline` | get purpose pipeline endpoint. |
| POST | `/api/purposes/{purpose_id}/start` | `backend.ai_org_backend.api.purposes.start_purpose` | Resume a paused purpose (idempotent). |
| GET | `/api/purposes/{purpose_id}/status` | `backend.ai_org_backend.api.pipeline.get_purpose_status` | get purpose status endpoint. |
| POST | `/api/register` | `backend.ai_org_backend.api.auth.register` | register endpoint. |
| POST | `/api/resume` | `backend.ai_org_backend.api.pipeline.resume_pipeline` | resume pipeline endpoint. |
| GET | `/api/settings/research` | `backend.ai_org_backend.api.settings.get_research_setting` | Return whether the current tenant allows web research. |
| POST | `/api/settings/research` | `backend.ai_org_backend.api.settings.set_research_setting` | Update the tenant's web research setting. |
| GET | `/api/settings/theme` | `backend.ai_org_backend.api.settings.get_theme_setting` | Return the current tenant's theme preference. |
| POST | `/api/settings/theme` | `backend.ai_org_backend.api.settings.set_theme_setting` | Update the tenant's theme preference (light or dark). |
| GET | `/api/templates` | `backend.ai_org_backend.api.templates.list_files` | list files endpoint. |
| GET | `/api/templates/{name}` | `backend.ai_org_backend.api.templates.get_file` | get file endpoint. |
| PUT | `/api/templates/{name}` | `backend.ai_org_backend.api.templates.save_file` | save file endpoint. |
| GET | `/health` | `backend.ai_org_backend.api.health.liveness` | Liveness probe — always 200 if the process is running. |
| GET | `/healthz` | `backend.ai_org_backend.api.health.liveness` | Liveness probe — always 200 if the process is running. |
| GET | `/livez` | `backend.ai_org_backend.api.health.liveness` | Liveness probe — always 200 if the process is running. |
| GET | `/readyz` | `backend.ai_org_backend.api.health.readiness` | Readiness probe — 200 only when all dependencies are reachable. |
| GET | `/reviews/{task_id}` | `backend.ai_org_backend.api.reviews.get_review` | get review endpoint. |
| POST | `/reviews/{task_id}/approve` | `backend.ai_org_backend.api.reviews.approve_review` | Mark the review as done; keeps owner 'Review'. |
| POST | `/task` | `backend.ai_org_backend.main.create_task` | create task endpoint. |
| WEBSOCKET | `/ws/chat/{purpose_id}` | `backend.ai_org_backend.api.chat.websocket_chat` | websocket chat endpoint. |
| WEBSOCKET | `/ws/status/{purpose_id}` | `backend.ai_org_backend.api.chat.websocket_status` | S6-#10.2: Real-time status push for a purpose. |

## Celery-Tasks

| Task | Handler | Verantwortung |
| --- | --- | --- |
| `agent.adjust_plan` | `backend.ai_org_backend.agents.adjust_plan.agent_adjust_plan` | Periodic planning adjuster – adds tasks for emerging risks and logs a summary. |
| `agent.architect` | `backend.ai_org_backend.agents.architect.architect_task` | Celery entry point for the architect agent. |
| `agent.architect_feedback` | `backend.ai_org_backend.agents.architect_feedback.architect_feedback_task` | Apply feedback to an architecture blueprint and persist a new revision. |
| `agent.code_review` | `backend.ai_org_backend.agents.code_review.code_review_task` | Analyze the codebase and record a review report. |
| `agent.dev` | `backend.ai_org_backend.agents.agent_dev.agent_dev` | Generate code for the given task using OpenAI. |
| `agent.e2e` | `backend.ai_org_backend.agents.e2e.e2e_task` | e2e task worker task. |
| `agent.insight` | `backend.ai_org_backend.agents.agent_insight.agent_insight` | Dummy insight agent: generate a summary of insights. |
| `agent.integration` | `backend.ai_org_backend.agents.agent_integration.agent_integration` | Dummy integration agent: finalize integration of all artifacts. |
| `agent.integration` | `backend.ai_org_backend.agents.integration.integration_task` | Generate & run integration tests for this purpose. |
| `agent.performance` | `backend.ai_org_backend.agents.performance.performance_task` | performance task worker task. |
| `agent.planner` | `backend.ai_org_backend.agents.planner.planner_task` | Celery task for Planner Agent: generates development tasks once blueprint and review are completed. |
| `agent.po` | `backend.ai_org_backend.agents.product_owner.agent_po` | Celery task that generates a PRD and persists it as an artefact. |
| `agent.project_manager` | `backend.ai_org_backend.agents.project_manager.agent_project_manager` | Periodic Project Management summary – generates a standup report and triggers alerts. |
| `agent.qa` | `backend.ai_org_backend.agents.agent_qa.agent_qa` | Generate a QA test report for the task using OpenAI. |
| `agent.refactor` | `backend.ai_org_backend.agents.refactor.refactor_task` | Analyze the codebase and suggest refactorings. |
| `agent.repo` | `backend.ai_org_backend.agents.repo_composer.agent_repo` | Generate initial project repository scaffolding (folders, files, CI stubs) and save as artifacts. |
| `agent.reviewer` | `backend.ai_org_backend.agents.reviewer.reviewer_task` | Celery entrypoint — creates the Markdown review artefact for the given review task. |
| `agent.security` | `backend.ai_org_backend.agents.security.security_task` | security task worker task. |
| `agent.telemetry` | `backend.ai_org_backend.main.agent_telemetry` | agent telemetry worker task. |
| `agent.ux_ui` | `backend.ai_org_backend.agents.agent_ux_ui.agent_ux_ui` | Generate a wireframe design for the task using OpenAI. |
| `agent.vision` | `backend.ai_org_backend.agents.vision.vision_task` | Celery task: generates the vision document asynchronously. |
| `ai_org_backend.tasks.llm_tasks.insight_agent` | `backend.ai_org_backend.tasks.llm_tasks.insight_agent` | Generate insights for a task via OpenAI and store artefact. |
| `architect.seed_graph` | `backend.ai_org_backend.agents.architect.seed_graph` | Legacy helper used by seed scripts. |
| `graph.reconcile` | `backend.ai_org_backend.tasks.graph_sync_task.reconcile_graph_task` | S3-14: Full reconciliation of SQL vs Neo4j for all tenants. |
| `graph.sync` | `backend.ai_org_backend.tasks.graph_sync_task.sync_graph_task` | S3-13: Incrementally sync SQL tasks/deps/artifacts to Neo4j. |
| `watchdog.detect_stuck_tasks` | `backend.ai_org_backend.tasks.watchdog_task.watchdog_detect_stuck_tasks` | Periodic watchdog: detect and requeue stuck tasks for all tenants. |

## Repositories

| Datei | Verantwortung |
| --- | --- |
| `backend/ai_org_backend/repo.py` | Unified Repo helper. |
| `backend/ai_org_backend/services/repo.py` | Repository helpers and budget accounting utilities. |
| `backend/ai_org_backend/services/repo_snapshot.py` | S5-A4: Repo Snapshot for Point-in-Time Consistency. |

## Services

| Datei | Verantwortung |
| --- | --- |
| `backend/ai_org_backend/services/approval.py` | Prüft und persistiert manuelle Freigaben für Review-/Release-Gates. |
| `backend/ai_org_backend/services/artifact_resolver.py` | Löst referenzierte Artefakte und deren aktuelle Versionen auf. |
| `backend/ai_org_backend/services/artifact_workflow.py` | Koordiniert Artefakt-Erstellung aus Purpose-, Task- und Chat-Kontext. |
| `backend/ai_org_backend/services/billing.py` | Berechnet und sammelt nutzungsbezogene Abrechnungsdaten. |
| `backend/ai_org_backend/services/budget.py` | Setzt Kostenbudgets und Budgetprüfungen für Tasks durch. |
| `backend/ai_org_backend/services/build_validator.py` | Validiert erzeugte Repository-Dateien vor Integration oder Release. |
| `backend/ai_org_backend/services/conflict_detector.py` | Erkennt konkurrierende Datei- und API-Änderungen zwischen Tasks. |
| `backend/ai_org_backend/services/cumulative_context.py` | Verdichtet Lauf- und Artefaktkontext für Folgeagenten. |
| `backend/ai_org_backend/services/cycle_detector.py` | Verhindert zyklische Task-Abhängigkeiten im DAG. |
| `backend/ai_org_backend/services/deep_research.py` | Führt quellenbasierte Recherche- und Syntheseabläufe aus. |
| `backend/ai_org_backend/services/deployment_generator.py` | Erzeugt Deployment-Artefakte für generierte Repositories. |
| `backend/ai_org_backend/services/feedback_loop.py` | Setzt bestehende Review-Fix-Rework-Schleifen um. |
| `backend/ai_org_backend/services/file_reservation.py` | Reserviert Dateien zur Kollisionsvermeidung paralleler Agenten. |
| `backend/ai_org_backend/services/graceful_shutdown.py` | Koordiniert Startup- und Shutdown-Hooks für Runtime-Komponenten. |
| `backend/ai_org_backend/services/graph_service.py` | Liefert Graph-Sichten über Tasks, Phasen und Artefakte. |
| `backend/ai_org_backend/services/graph_sync.py` | Spiegelt SQL-Task-Zustand nach Neo4j. |
| `backend/ai_org_backend/services/llm_client.py` | Kapselt Provider-spezifische LLM-Aufrufe. |
| `backend/ai_org_backend/services/llm_errors.py` | Normalisiert LLM-Provider-Fehler für Retry- und UI-Pfade. |
| `backend/ai_org_backend/services/memory.py` | Verwaltet langlebigen Kontext und Retrieval-Daten. |
| `backend/ai_org_backend/services/merge_service.py` | Integriert Agentenänderungen in das Zielrepository. |
| `backend/ai_org_backend/services/metrics_llm.py` | Erfasst token- und providerbezogene LLM-Metriken. |
| `backend/ai_org_backend/services/peer_context.py` | Stellt Agenten den Status paralleler Tasks bereit. |
| `backend/ai_org_backend/services/pipeline_templates.py` | Verwaltet Legacy-Phasentemplates und Task-Erzeugung daraus. |
| `backend/ai_org_backend/services/repo.py` | Exportiert den tenantbezogenen Repo-Adapter und Budgetfunktionen. |
| `backend/ai_org_backend/services/repo_snapshot.py` | Erstellt Dateisystem-Snapshots für Analyse und Review. |
| `backend/ai_org_backend/services/review_gate.py` | Entscheidet Review-Fix-Abschluss und Re-Review-Eskalation. |
| `backend/ai_org_backend/services/shared_contracts.py` | Definiert geteilte JSON-Schema- und Validierungsverträge. |
| `backend/ai_org_backend/services/storage.py` | Persistiert Artefakte im Workspace und in der Datenbank. |
| `backend/ai_org_backend/services/structured_logging.py` | Konfiguriert strukturierte Logs für API und Worker. |
| `backend/ai_org_backend/services/test_exec.py` | Führt Testbefehle für generierte oder bearbeitete Repos aus. |
| `backend/ai_org_backend/services/testing.py` | Bündelt Test-Hilfslogik für Runtime- und Agentenpfade. |
| `backend/ai_org_backend/services/token_counter.py` | Schätzt Tokenverbrauch für Prompts und Artefakte. |
| `backend/ai_org_backend/services/url_safety.py` | Validiert externe URLs vor Tool- oder Recherchezugriffen. |
| `backend/ai_org_backend/services/vector_store.py` | Verwaltet Embedding- und Vektorstore-Operationen. |

## Persistenzmodelle

| Datei | Verantwortung |
| --- | --- |
| `backend/ai_org_backend/models/artifact.py` | Definiert persistierte Datenstruktur(en): Artifact. |
| `backend/ai_org_backend/models/audit_log.py` | Definiert persistierte Datenstruktur(en): AuditAction, AuditLog. |
| `backend/ai_org_backend/models/chat.py` | Definiert persistierte Datenstruktur(en): ChatRole, ChatScope, ChatIntent, ChatMessageArtifact, ChatMessage, ChatThreadContext. |
| `backend/ai_org_backend/models/code_review_finding.py` | Definiert persistierte Datenstruktur(en): FindingSeverity, FindingCategory, CodeReviewFinding. |
| `backend/ai_org_backend/models/feedback.py` | Definiert persistierte Datenstruktur(en): FeedbackType, Feedback. |
| `backend/ai_org_backend/models/file_reservation.py` | Definiert persistierte Datenstruktur(en): FileReservation. |
| `backend/ai_org_backend/models/merge_conflict.py` | Definiert persistierte Datenstruktur(en): MergeConflictStatus, MergeConflict. |
| `backend/ai_org_backend/models/pipeline.py` | Definiert persistierte Datenstruktur(en): PipelineTemplate, PipelinePhase. |
| `backend/ai_org_backend/models/prompt_template.py` | Definiert persistierte Datenstruktur(en): PromptTemplate, TenantPromptAssignment. |
| `backend/ai_org_backend/models/purpose.py` | Definiert persistierte Datenstruktur(en): Purpose. |
| `backend/ai_org_backend/models/task.py` | Definiert persistierte Datenstruktur(en): TaskStatus, TaskOwner, Task. |
| `backend/ai_org_backend/models/task_dependency.py` | Definiert persistierte Datenstruktur(en): TaskDependency. |
| `backend/ai_org_backend/models/tenant.py` | Definiert persistierte Datenstruktur(en): UserTheme, Tenant. |

## Modul-Inventar

| Datei | Verantwortung |
| --- | --- |
| `backend/ai_org_backend/__init__.py` | ai_org_backend package init Enable Redis compatibility early so older callers of 'decrbyfloat' continue to work (internally via incrbyfloat with a negative value). |
| `backend/ai_org_backend/agents/__init__.py` | Agent package initialisation. |
| `backend/ai_org_backend/agents/adjust_plan.py` | Adjust plan module. |
| `backend/ai_org_backend/agents/agent_dev.py` | Agent dev module. |
| `backend/ai_org_backend/agents/agent_insight.py` | Agent insight module. |
| `backend/ai_org_backend/agents/agent_integration.py` | Agent integration module. |
| `backend/ai_org_backend/agents/agent_qa.py` | Agent qa module. |
| `backend/ai_org_backend/agents/agent_ux_ui.py` | Agent ux ui module. |
| `backend/ai_org_backend/agents/architect.py` | Architect agent utilities and Celery tasks. |
| `backend/ai_org_backend/agents/architect_feedback.py` | Celery task handling architecture blueprint revisions. |
| `backend/ai_org_backend/agents/code_review.py` | Code review module. |
| `backend/ai_org_backend/agents/e2e.py` | E2E / UAT Test Agent -------------------- Derives pytest-based E2E tests from PRD acceptance criteria, optionally using Playwright. |
| `backend/ai_org_backend/agents/integration.py` | Integration Test Agent ---------------------- Generates pytest-based integration tests (black-box over HTTP and optional UI), executes them, stores results, and raises fix tasks on failure. |
| `backend/ai_org_backend/agents/performance.py` | Performance Test Agent ---------------------- Generates a small Locustfile, executes a short headless run, evaluates p95 latency. |
| `backend/ai_org_backend/agents/planner.py` | Planner module. |
| `backend/ai_org_backend/agents/product_owner.py` | Agents responsible for creating and updating the Product Requirements Document. |
| `backend/ai_org_backend/agents/project_manager.py` | Project manager module. |
| `backend/ai_org_backend/agents/refactor.py` | Refactor module. |
| `backend/ai_org_backend/agents/repo_composer.py` | Celery agent to compose an initial repository structure based on the architecture plan. |
| `backend/ai_org_backend/agents/reviewer.py` | Reviewer module. |
| `backend/ai_org_backend/agents/security.py` | Security Agent -------------- Runs Bandit (Python static analysis) and pip-audit (deps). |
| `backend/ai_org_backend/agents/utils.py` | Utilities for agent modules. |
| `backend/ai_org_backend/agents/vision.py` | Vision module. |
| `backend/ai_org_backend/alembic/env.py` | Env module. |
| `backend/ai_org_backend/alembic/versions/20251207_init_schema.py` | Initial database schema creation. |
| `backend/ai_org_backend/alembic/versions/20260329_s1_cascade_and_constraints.py` | S1-02: Add CASCADE DELETE constraints and dependency type validation. |
| `backend/ai_org_backend/alembic/versions/20260329_s2_version_and_heartbeat.py` | S2-03/S2-06: Add version counter and last_heartbeat_at to Task table. |
| `backend/ai_org_backend/alembic/versions/20260329_s3_artifact_versioning.py` | S3-12: Add version_number and parent_id to Artifact table. |
| `backend/ai_org_backend/alembic/versions/20260330_s5_review_merge_tables.py` | S5: Add code_review_finding, merge_conflict tables + task review fields. |
| `backend/ai_org_backend/alembic/versions/20260330_s6_audit_log.py` | S6: Add audit_log table for security event tracking. |
| `backend/ai_org_backend/api/__init__.py` | TODO. |
| `backend/ai_org_backend/api/agents.py` | Agents module. |
| `backend/ai_org_backend/api/artifact_bridge.py` | Bridge API for exposing artifact details and feedback messages. |
| `backend/ai_org_backend/api/auth.py` | Auth module. |
| `backend/ai_org_backend/api/chat.py` | Chat module. |
| `backend/ai_org_backend/api/dependencies.py` | Dependencies module. |
| `backend/ai_org_backend/api/health.py` | S6-05: Health / Readiness / Liveness probe endpoints. |
| `backend/ai_org_backend/api/pipeline.py` | Pipeline module. |
| `backend/ai_org_backend/api/purposes.py` | Purposes module. |
| `backend/ai_org_backend/api/reviews.py` | Reviews module. |
| `backend/ai_org_backend/api/root.py` | Root module. |
| `backend/ai_org_backend/api/routes/__init__.py` | TODO. |
| `backend/ai_org_backend/api/routes/tasks.py` | TODO. |
| `backend/ai_org_backend/api/settings.py` | Settings endpoints for per-tenant toggles. |
| `backend/ai_org_backend/api/templates.py` | Templates module. |
| `backend/ai_org_backend/celeryconfig.py` | Celery configuration with task timeouts and resilience settings. |
| `backend/ai_org_backend/compat/__init__.py` | Init module. |
| `backend/ai_org_backend/compat/redis_compat.py` | Backfill for 'decrbyfloat' in redis-py: Redis has no DECRBYFLOAT; the correct command is INCRBYFLOAT with a negative value. |
| `backend/ai_org_backend/config.py` | Configuration utilities for ai_org_backend. |
| `backend/ai_org_backend/db.py` | Db module. |
| `backend/ai_org_backend/hooks/__init__.py` | Init module. |
| `backend/ai_org_backend/hooks/review_hook.py` | Review Hook (monkey-patch register_artefact) ------------------------------------------- We hook into `register_artefact` so that **whenever** the architecture blueprint Markdown is saved, we: 1) create (or reuse) a gating task "Architecture & Domain Review" 2) wire dependencies: blueprint -> review -> all other tasks 3) enqueue a Celery job to generate the review Markdown artefact This avoids invasive edits to pipeline/orchestrator and stays tenant-safe. |
| `backend/ai_org_backend/hooks/tests_hook.py` | Testing Hook ------------ Monkey-patch Repo.update to automatically schedule test stages: - After all non-test tasks are done -> create Integration Tests task and run it - After Integration done -> run E2E - After E2E done -> run Performance + Security This keeps orchestration simple & tenant-safe without heavy router edits. |
| `backend/ai_org_backend/main.py` | Main module. |
| `backend/ai_org_backend/metrics.py` | Prometheus metrics helpers and shared collectors. |
| `backend/ai_org_backend/middleware/__init__.py` | S6: Security & observability middleware stack. |
| `backend/ai_org_backend/middleware/exception_handler.py` | S6-04: Global exception handler with standardised error envelope. |
| `backend/ai_org_backend/middleware/input_sanitizer.py` | S6-09: Input sanitization middleware. |
| `backend/ai_org_backend/middleware/metrics_middleware.py` | S6-07: HTTP request metrics middleware for Prometheus. |
| `backend/ai_org_backend/middleware/rate_limit.py` | S6-01: In-process sliding-window rate limiter. |
| `backend/ai_org_backend/middleware/request_id.py` | S6-03: Request ID / Correlation ID middleware. |
| `backend/ai_org_backend/middleware/security_headers.py` | S6-02: Security headers middleware. |
| `backend/ai_org_backend/models/__init__.py` | Init module. |
| `backend/ai_org_backend/models/artifact.py` | Artifact module. |
| `backend/ai_org_backend/models/audit_log.py` | S6: Audit log model for security-relevant events. |
| `backend/ai_org_backend/models/chat.py` | Chat module. |
| `backend/ai_org_backend/models/code_review_finding.py` | S5-B4: Code Review Finding model. |
| `backend/ai_org_backend/models/feedback.py` | Feedback module. |
| `backend/ai_org_backend/models/file_reservation.py` | Reserviert Dateien zur Kollisionsvermeidung paralleler Agenten. |
| `backend/ai_org_backend/models/merge_conflict.py` | S5-B2: Merge Conflict model. |
| `backend/ai_org_backend/models/pipeline.py` | Pipeline template models defining configurable phase blueprints. |
| `backend/ai_org_backend/models/prompt_template.py` | Models for storing prompt templates and tenant assignments. |
| `backend/ai_org_backend/models/purpose.py` | Purpose module. |
| `backend/ai_org_backend/models/task.py` | Task module. |
| `backend/ai_org_backend/models/task_dependency.py` | Task dependency module. |
| `backend/ai_org_backend/models/tenant.py` | Tenant module. |
| `backend/ai_org_backend/orchestrator/__init__.py` | TODO. |
| `backend/ai_org_backend/orchestrator/cas.py` | S2-03: Compare-And-Swap helpers for optimistic locking on Task status. |
| `backend/ai_org_backend/orchestrator/core.py` | TODO. |
| `backend/ai_org_backend/orchestrator/executor.py` | TODO. |
| `backend/ai_org_backend/orchestrator/graph_orchestrator.py` | Graph orchestrator module. |
| `backend/ai_org_backend/orchestrator/inspector.py` | Inspector module. |
| `backend/ai_org_backend/orchestrator/locks.py` | S2-01: Distributed Redis locks for orchestrator phase transitions. |
| `backend/ai_org_backend/orchestrator/role_rules.py` | Role rules module. |
| `backend/ai_org_backend/orchestrator/router.py` | Router module. |
| `backend/ai_org_backend/orchestrator/scheduler.py` | Scheduler module. |
| `backend/ai_org_backend/orchestrator/watchdog.py` | S2-04 / S2-05 / S2-06: Stuck-task detector, dead-letter queue, and heartbeat. |
| `backend/ai_org_backend/redis_client.py` | Redis client module. |
| `backend/ai_org_backend/repo.py` | Exportiert den tenantbezogenen Repo-Adapter und Budgetfunktionen. |
| `backend/ai_org_backend/scripts/__init__.py` | Utility scripts package (seeders, one-off tasks). |
| `backend/ai_org_backend/scripts/seed_graph.py` | Seed graph module. |
| `backend/ai_org_backend/services/__init__.py` | TODO. |
| `backend/ai_org_backend/services/approval.py` | Prüft und persistiert manuelle Freigaben für Review-/Release-Gates. |
| `backend/ai_org_backend/services/artifact_resolver.py` | Löst referenzierte Artefakte und deren aktuelle Versionen auf. |
| `backend/ai_org_backend/services/artifact_workflow.py` | Koordiniert Artefakt-Erstellung aus Purpose-, Task- und Chat-Kontext. |
| `backend/ai_org_backend/services/billing.py` | Berechnet und sammelt nutzungsbezogene Abrechnungsdaten. |
| `backend/ai_org_backend/services/budget.py` | Setzt Kostenbudgets und Budgetprüfungen für Tasks durch. |
| `backend/ai_org_backend/services/build_validator.py` | Validiert erzeugte Repository-Dateien vor Integration oder Release. |
| `backend/ai_org_backend/services/conflict_detector.py` | Erkennt konkurrierende Datei- und API-Änderungen zwischen Tasks. |
| `backend/ai_org_backend/services/cumulative_context.py` | Verdichtet Lauf- und Artefaktkontext für Folgeagenten. |
| `backend/ai_org_backend/services/cycle_detector.py` | Verhindert zyklische Task-Abhängigkeiten im DAG. |
| `backend/ai_org_backend/services/deep_research.py` | Führt quellenbasierte Recherche- und Syntheseabläufe aus. |
| `backend/ai_org_backend/services/deployment_generator.py` | Erzeugt Deployment-Artefakte für generierte Repositories. |
| `backend/ai_org_backend/services/feedback_loop.py` | Setzt bestehende Review-Fix-Rework-Schleifen um. |
| `backend/ai_org_backend/services/file_reservation.py` | Reserviert Dateien zur Kollisionsvermeidung paralleler Agenten. |
| `backend/ai_org_backend/services/graceful_shutdown.py` | Koordiniert Startup- und Shutdown-Hooks für Runtime-Komponenten. |
| `backend/ai_org_backend/services/graph_service.py` | Liefert Graph-Sichten über Tasks, Phasen und Artefakte. |
| `backend/ai_org_backend/services/graph_sync.py` | Spiegelt SQL-Task-Zustand nach Neo4j. |
| `backend/ai_org_backend/services/llm_client.py` | Kapselt Provider-spezifische LLM-Aufrufe. |
| `backend/ai_org_backend/services/llm_errors.py` | Normalisiert LLM-Provider-Fehler für Retry- und UI-Pfade. |
| `backend/ai_org_backend/services/memory.py` | Verwaltet langlebigen Kontext und Retrieval-Daten. |
| `backend/ai_org_backend/services/merge_service.py` | Integriert Agentenänderungen in das Zielrepository. |
| `backend/ai_org_backend/services/metrics_llm.py` | Erfasst token- und providerbezogene LLM-Metriken. |
| `backend/ai_org_backend/services/peer_context.py` | Stellt Agenten den Status paralleler Tasks bereit. |
| `backend/ai_org_backend/services/pipeline_templates.py` | Verwaltet Legacy-Phasentemplates und Task-Erzeugung daraus. |
| `backend/ai_org_backend/services/repo.py` | Exportiert den tenantbezogenen Repo-Adapter und Budgetfunktionen. |
| `backend/ai_org_backend/services/repo_snapshot.py` | Erstellt Dateisystem-Snapshots für Analyse und Review. |
| `backend/ai_org_backend/services/review_gate.py` | Entscheidet Review-Fix-Abschluss und Re-Review-Eskalation. |
| `backend/ai_org_backend/services/shared_contracts.py` | Definiert geteilte JSON-Schema- und Validierungsverträge. |
| `backend/ai_org_backend/services/storage.py` | Persistiert Artefakte im Workspace und in der Datenbank. |
| `backend/ai_org_backend/services/structured_logging.py` | Konfiguriert strukturierte Logs für API und Worker. |
| `backend/ai_org_backend/services/test_exec.py` | Führt Testbefehle für generierte oder bearbeitete Repos aus. |
| `backend/ai_org_backend/services/testing.py` | Bündelt Test-Hilfslogik für Runtime- und Agentenpfade. |
| `backend/ai_org_backend/services/token_counter.py` | Schätzt Tokenverbrauch für Prompts und Artefakte. |
| `backend/ai_org_backend/services/url_safety.py` | Validiert externe URLs vor Tool- oder Recherchezugriffen. |
| `backend/ai_org_backend/services/vector_store.py` | Verwaltet Embedding- und Vektorstore-Operationen. |
| `backend/ai_org_backend/settings.py` | Centralized application settings. |
| `backend/ai_org_backend/tasks/__init__.py` | TODO. |
| `backend/ai_org_backend/tasks/celery_app.py` | Celery application instance for ai_org_backend tasks. |
| `backend/ai_org_backend/tasks/dynamic_worker.py` | Dynamic worker module. |
| `backend/ai_org_backend/tasks/graph_sync_task.py` | S3-13 / S3-14: Graph sync as Celery task with retry + periodic reconciliation. |
| `backend/ai_org_backend/tasks/llm_tasks.py` | LLM powered agent tasks. |
| `backend/ai_org_backend/tasks/watchdog_task.py` | S-Sprint3 Fix #11: Stuck-task watchdog as Celery Beat task. |
| `backend/ai_org_backend/utils/filetypes.py` | Filetypes module. |
| `backend/ai_org_backend/utils/llm.py` | Convenience wrappers around the unified LLM client. |
