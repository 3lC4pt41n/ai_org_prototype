# Phase 3 Template Library

Status: implemented as declarative graph families.

Templates live in `backend/ai_org_backend/graph/templates/*.yaml`. They are
JSON-compatible YAML so they can be loaded without adding a runtime dependency.

## Families

| Family | Intent Match | Shape |
| --- | --- | --- |
| `software_delivery` | `software/create/code_change|prd|implementation_plan` | vision -> PRD -> architecture -> review -> plan -> implementation -> QA -> release |
| `book_writing` | `book/create/manuscript` | outline/style/research -> chapter fan-out -> continuity -> bounded style repair -> review -> release |
| `research_brief` | `research/create|summarize/research_brief` | question -> source strategy -> source fan-out -> synthesis -> bias check -> review -> brief |
| `analysis_report` | `general|research/create/analysis_report` | question -> data scope -> extraction -> analysis -> cross-check -> report |
| `knowledge_base_update` | `general|ops|research/create|rework/knowledge_base_update` | source -> diff -> bounded consolidation -> reviewer -> publish |
| `architecture_rework` | `software/rework/architecture_blueprint` | load current -> impact -> bounded revise/review loop -> invalidate downstream -> publish |

## Matcher

`template_matcher.py` scores exact domain/action/deliverable matches:

- domain: 40 %
- action: 35 %
- deliverable type: 25 %

An exact family match scores `1.0`; `best_template(..., min_confidence=0.9)`
is used by tests and future graph compilation.

## Validation

`make graph-validate` loads every template, instantiates it as a
`PipelineGraph`, and runs Phase 2 validation. Loops are only accepted when they
declare `max_revisions`, `cost_budget`, and `convergence_predicate`.

## Failure Modes

- No match above threshold: Phase 8 synthesizer or explicit clarification.
- Invalid YAML/JSON: `make graph-validate` fails before runtime use.
- Unbounded feedback loop: Phase 2 validator rejects the template.
- High-risk runtime intent: Phase 2 validator requires approval nodes.
