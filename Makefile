# Simple commands for developer workflows.
# Tip: 'make help' shows all targets.

.RECIPEPREFIX := >
.PHONY: help install-dev fmt lint typecheck test ci

help:
> @echo "Targets:"
> @echo "  install-dev  - Install dev dependencies & pre-commit hooks"
> @echo "  fmt          - Format code (black + isort)"
> @echo "  lint         - Ruff lint with auto-fix"
> @echo "  typecheck    - mypy type check"
> @echo "  test         - Tests including coverage"
> @echo "  ci           - Lint + type check + tests (like CI)"

install-dev:
> pip install -r backend/ai_org_backend/requirements.txt
> pip install -e backend[dev]
> playwright install chromium
> pre-commit install

fmt:
> black .
> isort .

lint:
> ruff check --fix .

typecheck:
> mypy backend/ai_org_backend

test:
> PYTHONPATH=backend pytest -q --cov=ai_org_backend --cov-report=term-missing

ci: lint typecheck test
