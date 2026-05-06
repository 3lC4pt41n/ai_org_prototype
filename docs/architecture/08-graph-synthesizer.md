# Phase 8 Bounded Graph Synthesizer

Status: implemented with template fallback and hard limits.

## Algorithm

`compile_graph(intent)`:

1. matches templates from Phase 3,
2. uses the best template when confidence is sufficient,
3. otherwise synthesizes from the declared capability catalog,
4. inserts approval semantics for high-risk work,
5. validates the graph with Phase 2 rules.

## Hard Limits

- max 20 nodes,
- no synthesized loops,
- high-risk execution nodes require approval,
- estimated cost must fit `intent.constraints.budget.cost_eur` when present,
- only declared capabilities from `graph/capability_catalog/*.yaml` are used.

## Traceability

Compiled graphs annotate `intent.constraints["graph.origin"]` as:

- `template`,
- `synthesized`.

## Tests

`backend/tests/graph/test_synthesizer.py` covers template fallback, catalog-only
synthesis, high-risk approval insertion, budget rejection, and 20 adversarial
random intents.
