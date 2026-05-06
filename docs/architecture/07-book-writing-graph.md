# Phase 7 Book-Writing Graph

Status: implemented as deterministic domain capabilities plus smoke workflow.

## Capabilities

`backend/ai_org_backend/agents/book/workflow.py` provides:

- `plan_outline`,
- `write_chapter`,
- `continuity_check`,
- `style_harmonize`,
- `review_manuscript`,
- `run_book_smoke_workflow`.

The capabilities align with the `book_writing.v1` graph template from Phase 3.

## Acceptance Coverage

`backend/tests/book/test_book_workflow.py` verifies:

- an 8-chapter non-fiction smoke workflow produces an approved manuscript,
- continuity detects explicit adversarial inconsistency and duplicate chapters,
- a human style override can be applied before review without breaking the graph,
- lineage is attached per chapter to outline, styleguide, and research versions.

## Boundary

This phase implements backend domain behavior and graph-compatible capabilities.
Frontend visualization can consume the chapter statuses and lineage returned by
the workflow, but no existing frontend route is modified here.
