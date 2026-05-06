# Phase 5 Observability

Status: implemented as adapter-ready contracts.

## Trace

`observability/run_tracer.py` provides:

- request -> graph -> node -> tool_call -> llm_call span hierarchy support,
- PII scrubbing for prompt/raw content fields,
- bounded export size with truncation metadata.

The in-memory tracer is the default contract test implementation. OTel export
can be added behind the same surface without changing graph/node code.

## Lineage

`OpenLineageEmitter` emits OpenLineage-shaped `START`, `COMPLETE`, and `FAIL`
events with artifact IDs represented as datasets.

## Cost

`CostTracker` records provider/model/token/cost records and reports totals per
run and node.

## Dashboards

Dashboard stubs live in `dashboards/`:

- `run_health.json`,
- `graph_shape.json`,
- `cost_time.json`,
- `lineage.json`.

## Boundaries

This phase adds stable contracts and testable behavior. It does not require a
running Grafana, OTel collector, or OpenLineage backend in local development.
