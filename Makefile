# Einfache Kommandos für Developer-Workflows.
# Tipp: 'make help' zeigt alle Targets an.

.PHONY: help install-dev fmt lint typecheck test ci

help:
@echo "Targets:"
@echo "  install-dev  - Installiert Dev-Dependencies & pre-commit hooks"
@echo "  fmt          - Formatiert Code (black + isort)"
@echo "  lint         - Ruff-Lint mit Auto-Fix"
@echo "  typecheck    - mypy Typprüfung"
@echo "  test         - Tests inkl. Coverage"
@echo "  ci           - Lint + Typcheck + Tests (wie im CI)"

install-dev:
pip install -r backend/requirements.txt
pip install -r backend/requirements-dev.txt
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

ci: lint typecheck test
