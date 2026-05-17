**E2E Pipeline Audit Report**

ai_org_prototype – Version 2.0

Comprehensive End-to-End Audit

30\. March 2026

*Scope: Orchestrator, Agent Data Flow, Task Graph, Celery Workers, LLM Integration, Approval Gates, Multi-Agent Coordination, Repo Composer, Database Consistency, Frontend-Backend Sync*

Table of Contents

1\. Executive Summary

This report presents the findings of a comprehensive end-to-end audit of the ai_org_prototype pipeline – a platform for fully automated software creation through a chain of LLM agents. The audit systematically analyzed 10 critical areas covering the entire flow from project purpose input to final repository export.

**Key Statistics:**

|                              |           |                               |
|------------------------------|-----------|-------------------------------|
| **Metric**                   | **Count** | **Details**                   |
| Total Findings               | 25        | Across 10 audit areas         |
| Critical Findings            | 13        | Blocking E2E automation       |
| Medium Findings              | 12        | Impacting reliability         |
| Files Analyzed               | 60+       | Backend, Frontend, Prompts    |
| Blocking for Full Automation | 16        | Must fix before E2E auto-mode |

The audit reveals that the pipeline has a solid architectural foundation but contains critical gaps that prevent reliable fully automated (auto-mode) execution. The most severe issues cluster around: (1) phase gate validation – the orchestrator advances phases without verifying that artifacts actually exist; (2) data consistency – Neo4j and PostgreSQL can silently drift; (3) feedback loops – user feedback is collected but agents are never re-executed; and (4) conflict resolution – parallel agent outputs are only checked for conflicts after generation, not prevented beforehand.

2\. Risk Matrix

|  |  |  |  |  |
|----|----|----|----|----|
| **\#** | **Finding** | **Severity** | **Area** | **Blocks Auto?** |
| 1 | Phase Gate Advances Without Artifact Validation | **🔴 Critical** | 1: Orchestrator | Yes |
| 2 | Requires_Approval Gate Has Dead Code – Never Enforced | **🔴 Critical** | 1: Orchestrator | Yes |
| 3 | Race Condition Between Neo4j Leaf Query and PostgreSQL Dispatch | **🔴 Critical** | 1: Orchestrator | Yes |
| 4 | Feedback Injection Incomplete – Agents Never Re-Executed | **🔴 Critical** | 6: Approval/Feedback | Yes |
| 5 | Dual Approval Paths (REST vs WebSocket) Not Synchronized | **🔴 Critical** | 6: Approval/Feedback | Yes |
| 6 | Silent Neo4j Graph Sync Failures – No Rollback | **🔴 Critical** | 3: Task Graph | Yes |
| 7 | Runtime Edge Additions Can Create Cycles – No DAG Validation | **🔴 Critical** | 3: Task Graph | Yes |
| 8 | Conflict Detection Runs Too Late – Post-Generation Only | **🔴 Critical** | 7: Multi-Agent | Yes |
| 9 | Missing Artifact Fallback in Downstream Agents | **🔴 Critical** | 2: Data Flow | Yes |
| 10 | No Build/Syntax Validation After Repo Assembly | **🔴 Critical** | 8: Repo Composer | Yes |
| 11 | Tasks in 'DOING' Status Can Hang Indefinitely | **🔴 Critical** | 3: Task Graph | Yes |
| 12 | Approval Flow Not Gap-Free in Auto-Mode | **🔴 Critical** | 6: Approval/Feedback | Yes |
| 13 | Code Review Re-Review Loop Is Incomplete | **🟡 Medium** | 7: Multi-Agent | Yes |
| 14 | Double Budget Debit Per Task | **🟡 Medium** | 4: Celery Worker | No |
| 15 | No LLM Retry Backoff in Agents | **🟡 Medium** | 5: LLM Integration | No |
| 16 | No Explicit LLM Call Timeouts | **🟡 Medium** | 5: LLM Integration | No |
| 17 | Jinja2 Template Variable Validation Missing | **🟡 Medium** | 2: Data Flow | No |
| 18 | Cumulative Context Silently Truncated at 50K Chars | **🟡 Medium** | 2: Data Flow | No |
| 19 | Model Selection Hardcoded and Inconsistent Across Agents | **🟡 Medium** | 5: LLM Integration | No |
| 20 | Migration Chain Fragmented – Multiple Roots and No-Op Merges | **🔴 Critical** | 9: Database | Yes |
| 21 | Phase Slug Mismatch Risk Between Frontend and Backend | **🟡 Medium** | 10: Frontend | No |
| 22 | Auto-Mode Frontend Toggle Has No Backend Effect | **🟡 Medium** | 10: Frontend | Yes |
| 23 | Peer Context Is Advisory Only – No Hard Constraint Enforcement | **🟡 Medium** | 7: Multi-Agent | No |
| 24 | Polling-Based Status Updates (6s Interval) Instead of Real-Time | **🟡 Medium** | 10: Frontend | No |
| 25 | Planner JSON Schema Allows Additional Properties | **🟡 Medium** | 2: Data Flow | No |

3\. Detailed Findings

Area 1: Orchestrator & Phase-Transitions

Finding 1: Phase Gate Advances Without Artifact Validation

**Severity: 🔴 Critical**

**Files:** orchestrator/scheduler.py (lines 396-451, 755-794)

**Description:**

In auto mode, the orchestrator checks purpose_mode == 'auto' and immediately approves the phase gate even when NO artifact exists. A task with status=DONE but no artifact causes vision_approved = True. The pipeline advances with no actual deliverable.

**Impact:**

Downstream agents process empty/missing data. The entire E2E flow breaks silently when agents fail to produce output.

**Recommendation:**

Always require artifact existence: if purpose_mode == 'auto': approved = artifact is not None. Add explicit logging when artifact is missing.

------------------------------------------------------------------------

Finding 2: Requires_Approval Gate Has Dead Code – Never Enforced

**Severity: 🔴 Critical**

**Files:** orchestrator/scheduler.py (lines 95-100, 145-159, 269-300)

**Description:**

The requires_approval check at line 97-100 contains only 'pass' – it does nothing. A task's own requires_approval flag is never validated against its artifact state. Manual approval gates are effectively bypassed.

**Impact:**

Users cannot reliably enforce manual approval. Implementation phase can start before architecture review is approved.

**Recommendation:**

Implement self-check: if task.requires_approval and (not artifact or not artifact.released): return False

------------------------------------------------------------------------

Finding 3: Race Condition Between Neo4j Leaf Query and PostgreSQL Dispatch

**Severity: 🔴 Critical**

**Files:** orchestrator/scheduler.py (lines 836-853), orchestrator/locks.py

**Description:**

Between Neo4j LEAF_Q query and PostgreSQL recheck, another orchestrator instance or Celery callback can change task status. The dispatch lock has a fixed 120s TTL with no heartbeat renewal, meaning concurrent phase transitions are possible.

**Impact:**

Duplicate task dispatches, duplicate artifact generation, wasted LLM API costs, inconsistent state.

**Recommendation:**

Use CAS (Compare-And-Swap) on status update. Implement heartbeat-based lock renewal.

------------------------------------------------------------------------

Area 2: Agent-to-Agent Data Flow (Artifact Chain)

Finding 9: Missing Artifact Fallback in Downstream Agents

**Severity: 🔴 Critical**

**Files:** services/artifact_resolver.py, agents/planner.py (line 276)

**Description:**

load_by_phase() returns None if artifact not found. Agents silently proceed with empty strings. The Planner receives blueprint_md='' and generates task plans without architectural constraints.

**Impact:**

Downstream agents produce low-quality or incorrect output because upstream artifacts are missing. Pipeline 'succeeds' but produces garbage.

**Recommendation:**

Add explicit precondition checks: if required artifact is empty, fail the task explicitly. Or implement wait-for-artifact mechanism.

------------------------------------------------------------------------

Finding 17: Jinja2 Template Variable Validation Missing

**Severity: 🟡 Medium**

**Files:** agents/utils.py, all prompts/\*.j2

**Description:**

Templates are rendered without checking that all expected variables are in the context dict. Missing variables produce empty strings or raise errors at runtime.

**Impact:**

Prompts may contain empty sections, confusing the LLM. Template errors crash agents mid-execution.

**Recommendation:**

Add template context validator that checks all expected variables before rendering.

------------------------------------------------------------------------

Finding 18: Cumulative Context Silently Truncated at 50K Chars

**Severity: 🟡 Medium**

**Files:** services/cumulative_context.py

**Description:**

load_cumulative_context() truncates each phase artifact to 50,000 characters by default with a silent '\[... truncated ...\]' marker. No warning or log.

**Impact:**

Critical context lost without notification. Agents produce output based on incomplete information.

**Recommendation:**

Log warnings on truncation. Consider summarization instead of hard truncation.

------------------------------------------------------------------------

Finding 25: Planner JSON Schema Allows Additional Properties

**Severity: 🟡 Medium**

**Files:** agents/planner.py (lines 71-107)

**Description:**

TASKS_SCHEMA has additionalProperties: True. LLM can include random fields that break downstream parsing. Retry prompt doesn't include schema details.

**Impact:**

Task objects may contain unexpected fields. Retry attempts are low-quality without schema feedback.

**Recommendation:**

Set additionalProperties: false. Include schema in retry error_note.

------------------------------------------------------------------------

Area 3: Task-Graph & Dependency Resolution

Finding 6: Silent Neo4j Graph Sync Failures – No Rollback

**Severity: 🔴 Critical**

**Files:** repo.py (lines 49-65), services/graph_sync.py

**Description:**

Task updates are committed to PostgreSQL BEFORE attempting Neo4j sync. If Neo4j fails, SQL is already persisted. The code only logs errors, creating a divergent state where SQL is updated but Neo4j is stale.

**Impact:**

SQL and Neo4j graphs drift silently. Ready-task decisions are based on outdated Neo4j state. Pipeline execution order becomes incorrect.

**Recommendation:**

Implement message queue for deferred Neo4j updates with retry. Add periodic reconciliation task to detect/fix drift.

------------------------------------------------------------------------

Finding 7: Runtime Edge Additions Can Create Cycles – No DAG Validation

**Severity: 🔴 Critical**

**Files:** services/cycle_detector.py, repo.py (lines 142-152)

**Description:**

Cycle detection only runs during seeding. The repo.link() method allows adding new dependencies at runtime WITHOUT any cycle validation. An edge added via repo.link() could create a cycle that breaks the DAG assumption.

**Impact:**

Tasks locked in circular dependencies forever. LEAF_Q query will never identify 'ready' tasks in a cycle. Pipeline deadlocks.

**Recommendation:**

Add cycle detection to repo.link() before persisting. Use topological sort to validate DAG before edge insertion.

------------------------------------------------------------------------

Finding 11: Tasks in 'DOING' Status Can Hang Indefinitely

**Severity: 🔴 Critical**

**Files:** models/task.py (lines 119-122), celeryconfig.py

**Description:**

Task model has last_heartbeat_at but no monitoring loop checks for stale heartbeats. If a worker crashes while task is 'doing', the task remains stuck forever. Watchdog threshold (900s) exceeds hard timeout (600s) by 5 minutes.

**Impact:**

Stuck tasks block dependent tasks from becoming 'ready'. Pipeline stalls silently.

**Recommendation:**

Implement watchdog that queries for tasks where status='doing' AND last_heartbeat_at \< now() - 10min. Transition to 'failed'.

------------------------------------------------------------------------

Area 4: Celery Worker & Task Execution

Finding 14: Double Budget Debit Per Task

**Severity: 🟡 Medium**

**Files:** orchestrator/scheduler.py (lines 318, 896), tasks/celery_app.py

**Description:**

Budget is debited both in \_dispatch_task() (line 318) and in the orchestrator main loop (line 896). Non-pipeline tasks also get debited twice.

**Impact:**

Budget tracking is incorrect. Users see budget consumed by phantom debits.

**Recommendation:**

Consolidate debit into single location (scheduler only). Use atomic check_and_debit().

------------------------------------------------------------------------

Area 5: LLM-Integration & Error Handling

Finding 15: No LLM Retry Backoff in Agents

**Severity: 🟡 Medium**

**Files:** services/llm_client.py, services/llm_errors.py

**Description:**

resilient_llm_call() exists with exponential backoff but agents call chat_with_tools() directly. Rate limits and transient errors cause immediate task failure.

**Impact:**

Transient LLM errors cascade into permanent task failures in multi-agent scenarios.

**Recommendation:**

All agents should use resilient_llm_call() instead of chat_with_tools() directly.

------------------------------------------------------------------------

Finding 16: No Explicit LLM Call Timeouts

**Severity: 🟡 Medium**

**Files:** services/llm_client.py (lines 304-423)

**Description:**

chat_with_tools() and underlying OpenAI/Anthropic client calls don't specify timeouts. For 'o3'/'o3-pro' models, calls can hang indefinitely.

**Impact:**

Architect and Planner agents may hang indefinitely if LLM is slow. Task queue fills with hanging tasks.

**Recommendation:**

Add timeout parameter (default 300s, 900s for reasoning models). Catch TimeoutError for retry.

------------------------------------------------------------------------

Finding 19: Model Selection Hardcoded and Inconsistent Across Agents

**Severity: 🟡 Medium**

**Files:** agents/architect.py, agents/planner.py, agents/agent_dev.py

**Description:**

Architect uses 'o3' hardcoded, Planner uses 'o3' with 'o3-pro' fallback, DevAgent uses 'gpt-4o-mini'. No centralized model selection strategy.

**Impact:**

Difficult to manage model versions or switch providers globally. No cost visibility.

**Recommendation:**

Create centralized ModelSelector service with per-agent-tier configuration.

------------------------------------------------------------------------

Area 6: Approval-Gates & Feedback-Loop

Finding 4: Feedback Injection Incomplete – Agents Never Re-Executed

**Severity: 🔴 Critical**

**Files:** services/feedback_loop.py (lines 44-303), api/chat.py (lines 431-461)

**Description:**

User feedback is saved to DB, but redispatch_agent() is never triggered from the REST chat.py path. The feedback context is loaded during agent execution, but only if the task is re-dispatched – which never happens.

**Impact:**

User feedback is collected but agents are never re-executed with that feedback. The pipeline stalls after feedback is provided.

**Recommendation:**

After integrate_prd_feedback(), call redispatch_agent() to reset task status and re-queue the agent with feedback context.

------------------------------------------------------------------------

Finding 5: Dual Approval Paths (REST vs WebSocket) Not Synchronized

**Severity: 🔴 Critical**

**Files:** api/chat.py (lines 825-879), services/approval.py (lines 80-231)

**Description:**

Two independent approval mechanisms: centralized REST approve_artifact() service and a WebSocket direct approval path that bypasses the service entirely. WebSocket mutates artifact.released directly without idempotency checking or pause-flag clearing.

**Impact:**

Approval state becomes inconsistent. Double-approvals via WebSocket are not protected. Pause flags may not clear consistently.

**Recommendation:**

Route all WebSocket approvals through the centralized approval service.

------------------------------------------------------------------------

Finding 12: Approval Flow Not Gap-Free in Auto-Mode

**Severity: 🔴 Critical**

**Files:** hooks/review_hook.py (lines 35-194), models/pipeline.py

**Description:**

In auto-mode, the orchestrator can dispatch downstream tasks even if the architecture review artifact hasn't been released – task_status=='done' is the only gate, not artifact.released.

**Impact:**

Pipeline advances past review without actual review artifact being validated. Auto-mode is unreliable.

**Recommendation:**

Add artifact.released check for all approval-gated phases, even in auto-mode.

------------------------------------------------------------------------

Area 7: Implementation Phase – Multi-Agent Coordination

Finding 8: Conflict Detection Runs Too Late – Post-Generation Only

**Severity: 🔴 Critical**

**Files:** services/conflict_detector.py, agents/code_review.py, services/merge_service.py

**Description:**

Conflicts are detected only in code_review_task (after dev agents complete) and merge_service (after implementation phase). No pre-generation synchronization lock or reservation system exists. Two Dev agents can simultaneously write to the same file.

**Impact:**

Wasted compute on conflicting code. Merge phase must create fix tasks, re-dispatch agents, and re-review – extending execution time significantly.

**Recommendation:**

Implement file-ownership reservation: before a Dev agent starts, it claims exclusive write access to specific files. If conflict detected, wait or reassign.

------------------------------------------------------------------------

Finding 13: Code Review Re-Review Loop Is Incomplete

**Severity: 🟡 Medium**

**Files:** services/review_gate.py (lines 151-265), agents/code_review.py

**Description:**

Fix tasks are created and block the review task, but dispatch_re_review() is never automatically triggered when fix tasks complete. The review remains in 'changes_requested' indefinitely.

**Impact:**

Fix tasks complete but review is never re-triggered. Feedback loop (Review → Rework → Re-Review) is broken.

**Recommendation:**

Add a task completion hook that calls dispatch_re_review() when all fix tasks for a review are done.

------------------------------------------------------------------------

Finding 23: Peer Context Is Advisory Only – No Hard Constraint Enforcement

**Severity: 🟡 Medium**

**Files:** services/peer_context.py, agents/agent_dev.py

**Description:**

Peer task descriptions are injected as advisory text in prompts. Agents are instructed to 'avoid conflicts' but no programmatic enforcement exists.

**Impact:**

Agents generate conflicting code (duplicate endpoints, overlapping files) without hard constraints.

**Recommendation:**

Implement file-ownership reservation system. Block agent from writing to files claimed by another agent.

------------------------------------------------------------------------

Area 8: Repo Composer & Artifact Aggregation

Finding 10: No Build/Syntax Validation After Repo Assembly

**Severity: 🔴 Critical**

**Files:** agents/repo_composer.py, services/storage.py

**Description:**

The repo_composer generates file scaffolding but performs zero validation. No syntax checks, linting, dependency validation, or build testing. LLM output is parsed as JSON and saved directly to disk.

**Impact:**

Invalid, non-compilable repositories can be generated and released to users. No early detection of missing imports or syntax errors.

**Recommendation:**

Implement post-generation validation: py_compile for Python, eslint for JS/TS. Block release if critical syntax errors exist.

------------------------------------------------------------------------

Area 9: Database Consistency & Migrations

Finding 20: Migration Chain Fragmented – Multiple Roots and No-Op Merges

**Severity: 🔴 Critical**

**Files:** migrations/versions/

**Description:**

Non-linear migration history with multiple root migrations, split directories (migrations/ vs alembic/), and a no-op merge migration (20251207_merge_heads).

**Impact:**

New environments may apply partial migration history. Schema divergence across deployments.

**Recommendation:**

Consolidate into single directory. Create explicit merge migration. Add CI check: alembic branches should return empty.

------------------------------------------------------------------------

Area 10: Frontend-Backend Synchronization

Finding 21: Phase Slug Mismatch Risk Between Frontend and Backend

**Severity: 🟡 Medium**

**Files:** frontend phaseConfig.ts, backend api/pipeline.py

**Description:**

Frontend defines phase IDs as constants. Backend uses slug field in PipelinePhase. No validation that they match. A backend rename silently breaks the UI.

**Impact:**

UI may not display status correctly for renamed phases.

**Recommendation:**

Create shared API endpoint /api/pipeline/phases that returns canonical phase slug list.

------------------------------------------------------------------------

Finding 22: Auto-Mode Frontend Toggle Has No Backend Effect

**Severity: 🟡 Medium**

**Files:** frontend PurposePhase.tsx, backend api/purposes.py

**Description:**

Frontend sends PATCH to update mode to 'auto' but the backend only saves the flag. No orchestration task is triggered. Auto-mode has no visible effect on pipeline execution.

**Impact:**

Users can set auto-mode but nothing happens. Pipeline still requires manual intervention.

**Recommendation:**

When mode flips to 'auto', trigger Celery task that auto-approves and dispatches next phases.

------------------------------------------------------------------------

Finding 24: Polling-Based Status Updates (6s Interval) Instead of Real-Time

**Severity: 🟡 Medium**

**Files:** frontend PurposePhase.tsx

**Description:**

Frontend polls every 6 seconds. WebSocket exists but only for chat, not task/phase status. Up to 6s latency before UI reflects changes.

**Impact:**

Not real-time. 240 requests per 24 minutes even when nothing changes. Poor UX during auto-mode.

**Recommendation:**

Implement SSE or extend WebSocket to broadcast task status events.

------------------------------------------------------------------------

4\. Prioritized Recommendations (Top 10)

|  |  |  |  |
|----|----|----|----|
| **Priority** | **Recommendation** | **Description** | **Findings** |
| **P0** | Require Artifact Existence at Phase Gates | Before advancing to the next phase, validate that an artifact exists and is non-empty. This is the single most impactful fix – it prevents the entire pipeline from progressing with missing data. | \#1, \#9, \#12 |
| **P0** | Implement Centralized Approval Service | Route ALL approval paths (REST, WebSocket, auto-mode) through a single approve_artifact() function with idempotency, pause-flag clearing, and audit logging. | \#2, \#5, \#12 |
| **P0** | Fix Feedback Re-Execution Loop | When user provides feedback, call redispatch_agent() to reset the task and re-execute with feedback context. Without this, user feedback has no effect. | \#4, \#13 |
| **P0** | Add Cycle Detection to Runtime Edge Additions | Validate DAG integrity in repo.link() before persisting new dependencies. Use topological sort and reject cyclic edges with HTTP 409. | \#7 |
| **P1** | Implement Stuck Task Watchdog | Add periodic Celery beat job that queries for tasks with status='doing' AND stale heartbeats. Transition to 'failed' after threshold. Align watchdog with Celery hard timeout. | \#3, \#11 |
| **P1** | Add Graph Sync Retry with Reconciliation | Queue Neo4j updates via Celery with retry/backoff. Run periodic reconciliation (every 10 min) to detect and fix SQL/Neo4j drift. | \#6 |
| **P1** | Implement Pre-Generation Conflict Prevention | Add file-ownership reservation system. Before a Dev agent starts, it claims exclusive write access to specific files. Block conflicting writes. | \#8, \#23 |
| **P1** | Add Post-Assembly Build Validation | After repo_composer completes, run syntax checks (py_compile, eslint), dependency validation, and basic build tests. Block release if validation fails. | \#10 |
| **P2** | Wrap All LLM Calls in resilient_llm_call() | Ensure all agents use the existing retry/backoff wrapper with fallback model escalation. Add explicit timeouts (300s default, 900s for reasoning models). | \#15, \#16 |
| **P2** | Consolidate Migration Chain | Merge split migration directories, resolve non-linear history, remove no-op merge migration. Add CI check that alembic branches returns empty. | \#20 |

5\. Auto-Mode Assessment

The fully automated (auto-mode) pipeline is the core goal of the platform. This section assesses each phase's readiness for unsupervised execution.

|  |  |  |  |
|----|----|----|----|
| **Phase** | **Auto-Ready?** | **Severity** | **Blocking Issue** |
| Vision → PRD | Partial | Critical | Phase gate advances without artifact validation (#1) |
| PRD → Architecture | Partial | Critical | Feedback not re-executed (#4), cumulative context truncated (#18) |
| Architecture → Review | No | Critical | Approval not gap-free in auto-mode (#12), dual paths (#5) |
| Review → Planner | No | Critical | Missing artifact fallback (#9), requires_approval dead code (#2) |
| Planner → Implementation | Partial | Critical | Runtime cycles possible (#7), stuck tasks (#11) |
| Implementation (parallel) | No | Critical | Conflict detection post-hoc (#8), no re-review loop (#13) |
| Release | No | Critical | No build validation (#10), auto-mode toggle ineffective (#22) |

**Verdict:** The auto-mode pipeline is NOT production-ready. Zero phases are fully auto-ready. Addressing the P0 recommendations would unblock 4 of 7 phase transitions. Full auto-mode readiness requires resolving all P0 and P1 items.
