# Phase 9 Workflow Search

Status: optional experimental module implemented with hard bounds.

## Scope

`workflow_search.py` ranks existing template/synthesized graph candidates. It
does not invent capabilities, does not modify runtime state, and does not run
unbounded optimization.

## Bounds

`WorkflowSearchLimits` enforces:

- max 20 candidates,
- max 10 iterations,
- minimum acceptance score.

The default is intentionally conservative: 5 candidates, 3 iterations,
`min_score=0.75`.

## Scoring

The first scoring function combines:

- template match confidence,
- small approval-gate bonus,
- graph-size complexity penalty.

This is deliberately simple and deterministic until there is enough production
trace data from Phase 5 to support stronger optimization.
