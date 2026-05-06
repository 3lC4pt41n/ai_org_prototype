# Phase 2 PipelineGraph v2

Status: implemented as an additive contract layer.

## Decision

Legacy pipeline phases remain the execution source of truth for the current
runtime. Phase 2 adds explicit, typed graph contracts above them:

- `PipelineGraph`,
- `PipelineNode`,
- `PipelineEdge`,
- `WorkflowEngine`,
- `CeleryEngine` compatibility adapter,
- legacy phase adapter,
- graph validator,
- persistence migration for graph/run tables.

No existing Celery task or phase template is replaced in this phase.

## Validation Rules

`backend/ai_org_backend/graph/validator.py` rejects:

- duplicate node IDs,
- missing edge endpoints,
- unreachable dead nodes,
- data edges with incompatible schema types,
- unbounded cycles,
- high-risk execution nodes without approval,
- unresolved intent artifact references when an artifact lookup is supplied.

Feedback cycles are only valid when at least one node in the cycle declares all
bounded-loop controls: `max_revisions`, `cost_budget`, and
`metadata.convergence_predicate`.

## Migration

`20260506_phase2_pipeline_graph.py` creates:

- `pipeline_graphs`,
- `pipeline_nodes`,
- `pipeline_edges`,
- `runs`.

The existing task, phase, heartbeat, DLQ, and approval tables remain unchanged.

## Developer Commands

- `make graph-validate`
- `PYTHONPATH=backend python3 -m unittest discover -s backend/tests/graph`

## Boundary

Phase 2 is contract and adapter work only. Template families are introduced in
Phase 3; dynamic synthesis remains Phase 8.
