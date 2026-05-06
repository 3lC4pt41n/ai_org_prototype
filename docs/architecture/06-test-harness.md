# Phase 6 Five-Layer Test Harness

Status: implemented as a standard-library executable harness.

## Layers

| Layer | Location |
| --- | --- |
| Unit / Contract | `backend/tests/contracts` |
| Graph Validation | `backend/tests/graph` |
| Replay | `backend/tests/replay` |
| Evaluator / Golden Set | `backend/tests/eval` |
| Chaos / Failure Injection | `backend/tests/chaos` |

Additional phase-specific tests for intent, rework, and observability are also
included in `make test-all`.

## Command

`make test-all`

This command uses `unittest` so the harness can run in minimal local
environments where `pytest` is not installed.

## Contracts

- Replay digests ignore volatile timestamp fields.
- Chaos provider-outage simulation verifies checkpoint resume idempotence.
- Rubric scoring supports deterministic golden-set checks.
- Contract validation catches missing and unexpected fields.

Full CI can still run the existing pytest suite when the development
dependencies are installed.
