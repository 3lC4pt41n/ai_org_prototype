# Simple commands for developer workflows.
# Tip: 'make help' shows all targets.

.PHONY: help install-dev fmt lint typecheck test test-all audit graph-validate ci

help:
	@echo "Targets:"
	@echo "  install-dev  - Install dev dependencies & pre-commit hooks"
	@echo "  fmt          - Format code (black + isort)"
	@echo "  lint         - Ruff lint with auto-fix"
	@echo "  typecheck    - mypy type check"
	@echo "  test         - Tests including coverage"
	@echo "  test-all     - Run Phase 6 five-layer unittest harness"
	@echo "  audit        - Generate architecture audit reports"
	@echo "  graph-validate - Validate PipelineGraph contracts/templates"
	@echo "  ci           - Lint + type check + tests (like CI)"

install-dev:
	pip install -r backend/ai_org_backend/requirements.txt
	pip install -e backend[dev]
	playwright install chromium
	pre-commit install

fmt:
	black .
	isort .

lint:
	ruff check --fix .

typecheck:
	mypy backend/ai_org_backend

test:
	PYTHONPATH=backend pytest -q --cov=ai_org_backend --cov-report=term-missing

test-all:
	PYTHONPATH=backend python3 scripts/test_all_layers.py

audit:
	PYTHONPATH=backend python3 scripts/generate_architecture_audit.py

graph-validate:
	PYTHONPATH=backend python3 scripts/validate_graphs.py

ci: lint typecheck test
