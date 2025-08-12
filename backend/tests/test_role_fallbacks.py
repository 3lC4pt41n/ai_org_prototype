from ai_org_backend.orchestrator.role_rules import heuristic_role, normalize_role


def test_heuristic_ux_ui_en_de():
    assert heuristic_role("Create React frontend with Tailwind") == "ux_ui"
    assert heuristic_role("Entwirf UI Wireframes (Benutzeroberfläche)") == "ux_ui"


def test_heuristic_qa_en_de():
    assert heuristic_role("Write E2E integration tests for login") == "qa"
    assert heuristic_role("Akzeptanztests für Upload-Flow ergänzen") == "qa"
    # explicit hint
    assert heuristic_role("agent.e2e: run browser E2E suite") == "qa"


def test_heuristic_telemetry_perf_and_security():
    assert heuristic_role("Run Locust load test, check p95 latency") == "telemetry"
    assert heuristic_role("Sicherheitsscan mit Bandit und OWASP Top10") == "telemetry"
    assert heuristic_role("agent.security: run pip-audit") == "telemetry"


def test_heuristic_repo_arch_product_review_refactor():
    assert heuristic_role("Init repository scaffolding & CI pipeline") == "repo"
    assert heuristic_role("Create architecture blueprint and ADR") == "architect"
    assert heuristic_role("Write PRD with acceptance criteria") == "product"
    assert heuristic_role("Perform code review + static analysis") == "qa_review"
    assert heuristic_role("Refactor modules and cleanup duplicates") == "qa_refactor"


def test_normalize_role_variants():
    assert normalize_role("frontend") == "ux_ui"
    assert normalize_role("Testing") == "qa"
    assert normalize_role("Performance") == "telemetry"
    assert normalize_role("Architecture") == "architect"
    assert normalize_role("PRD") == "product"
    assert normalize_role("code review") == "qa_review"
    assert normalize_role("refactoring") == "qa_refactor"
    assert normalize_role("dev") == "dev"
