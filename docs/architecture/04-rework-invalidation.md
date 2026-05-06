# Phase 4 Bounded Rework And Invalidation

Status: implemented as a central service contract.

## Decision

Rework is represented by a mandatory `RevisionLimitPolicy`:

- `max_revisions`,
- `convergence_predicate`,
- `cost_budget`.

All three are required. Missing bounds are validation errors.

## Artifact Invalidation

`ArtifactGraph.mark_downstream_stale(changed_artifact_id)` traverses artifact
dependencies transitively:

- `derived_from` marks downstream artifacts `stale`,
- `invalidates` marks downstream artifacts `invalidated`,
- `lowest_recompute_points()` returns direct derived children, so recomputation
  starts at the lowest needed downstream point rather than the pipeline root.

## Runtime Integration Boundary

The service is additive and pure. Existing `feedback_loop.py` and
`review_gate.py` remain operational until future runtime wiring migrates callers
to `services/rework.py`.

## Migration

`20260506_phase4_artifact_status.py` adds `artifact.status` with:

- `fresh`,
- `stale`,
- `invalidated`,
- `archived`.

## Tests

`backend/tests/rework/test_rework_service.py` covers stale propagation,
invalidating edges, convergence, revision-limit termination, and budget approval.
