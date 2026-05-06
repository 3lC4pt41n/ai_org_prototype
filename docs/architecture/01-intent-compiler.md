# Phase 1 Intent Compiler

Status: implemented.

## Decision

Incoming user requests are compiled into `UserIntent` before they enter legacy role
routing or future graph selection. The compiler is a cascade:

1. deterministic signal extraction,
2. artifact/context resolution,
3. optional structured LLM fallback,
4. deterministic validation,
5. confidence/clarification gate,
6. temporary legacy-role adapter.

The runtime remains unchanged below this layer. Legacy agent queues continue to
receive a role via `legacy_role_for_intent()` until Phase 2 introduces
`PipelineGraph` v2.

## Modules

| Module | Responsibility |
| --- | --- |
| `backend/ai_org_backend/intent/schema.py` | Defines the multi-axis `UserIntent` contract. |
| `backend/ai_org_backend/intent/extractor.py` | Extracts deterministic domain/action/deliverable signals. |
| `backend/ai_org_backend/intent/resolver.py` | Resolves referenced artifacts without importing runtime services. |
| `backend/ai_org_backend/intent/classifier.py` | Produces deterministic intents and optional structured LLM fallback. |
| `backend/ai_org_backend/intent/validator.py` | Enforces consistency and clarification-gate rules. |
| `backend/ai_org_backend/intent/compiler.py` | Orchestrates the cascade and maps intents to legacy roles. |
| `backend/ai_org_backend/api/intent.py` | Exposes compile, validate, read, edit, and approve-review endpoints. |
| `backend/ai_org_backend/models/intent_review.py` | Persists UI-visible intent drafts before execution. |

## API

| Endpoint | Purpose |
| --- | --- |
| `POST /api/intent/compile` | Compile a request without persistence. |
| `POST /api/intent/validate` | Validate a manually edited `UserIntent`. |
| `POST /api/intent/reviews` | Compile and persist an intent draft for UI review. |
| `GET /api/intent/reviews/{review_id}` | Read a persisted intent draft. |
| `PATCH /api/intent/reviews/{review_id}` | Edit, revalidate, validate, approve, or supersede a draft. |

`approved` is rejected while the intent still requires clarification.

## Clarification Gate

An intent requires clarification when validation reports any issue, including:

- `confidence < 0.75`,
- `action=rework` without a target artifact,
- unresolved rework target,
- domain/deliverable mismatch,
- high-risk work in `auto` mode.

The compiler adds a `clarification_node` marker into `intent.constraints` so
Phase 2 can translate it into a graph node without changing Phase 1 behavior.

## Acceptance Coverage

- The examples “bitte als Architekt das System X überarbeiten” and “bitte ein
  neues System X entwerfen” produce different `action` and target semantics.
- `backend/tests/intent/test_intent_compiler.py` contains 30 golden cases plus
  at least 5 adversarial clarification-gate cases.
- `trace.name = intent.compile` and key intent attributes are emitted as a stub
  trace payload in `CompiledIntent.trace`.
- UI correction is supported through persisted `IntentReview` drafts.

## Known Boundaries

The LLM fallback is explicit (`use_llm_fallback=true`) and disabled by default
to preserve deterministic latency and avoid hidden provider calls. Phase 2 will
consume the compiled intent for graph selection; Phase 1 only prepares and
validates semantics.
