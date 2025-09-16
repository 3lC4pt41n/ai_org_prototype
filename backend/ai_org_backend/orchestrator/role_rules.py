from __future__ import annotations

"""
Keyword-driven role heuristics for robust task routing.

Why this file?
  - The LLM role classifier is good but not perfect. We add a simple, explainable
    keyword fallback so obvious tasks (e.g., “UI”, “E2E”, “performance”, “Bandit”)
    get consistently routed even if the LLM output is noisy or ambiguous.
  - Supports English + German keywords.

How it works:
  - `heuristic_role(text)`: returns a canonical role (str) if strong keywords match,
    else None so the caller can continue with LLM classification.
  - `normalize_role(s)`: maps common synonyms / model outputs to canonical roles.

Canonical roles (kept small & stable to match router -> queues):
  - dev, ux_ui, qa, telemetry, repo, architect, product, qa_review, qa_refactor
"""

import re  # noqa: E402
from typing import Dict, List, Optional, Tuple  # noqa: E402

# Canonical roles the router understands (must match router mapping)
CANONICAL_ROLES = {
    "dev",
    "ux_ui",
    "qa",
    "telemetry",
    "repo",
    "architect",
    "product",
    "qa_review",
    "qa_refactor",
    "reviewer",
}

_RULES: List[Tuple[str, re.Pattern]] = []


def _build_rules() -> List[Tuple[str, re.Pattern]]:
    rules: List[Tuple[str, re.Pattern]] = []

    def pat(words: List[str]) -> re.Pattern:
        """
        Build a single regex that matches any of the given words.
        We use case-insensitive matching and allow hyphenated tokens like 'end-to-end'.
        """
        expr = r"(" + "|".join(re.escape(w) for w in words) + r")"
        return re.compile(expr, re.IGNORECASE)

    # UI / Frontend (EN + DE)
    rules.append(
        (
            "ux_ui",
            pat(
                [
                    "ui",
                    "ux",
                    "frontend",
                    "react",
                    "vue",
                    "tailwind",
                    "css",
                    "scss",
                    "html",
                    "component",
                    "components",
                    "wireframe",
                    "design",
                    "figma",
                    "oberfläche",
                    "benutzeroberfläche",
                    "ansicht",
                    "komponente",
                    "stylesheet",
                ]
            ),
        )
    )

    # Product / Requirements
    rules.append(
        (
            "product",
            pat(
                [
                    "prd",
                    "requirements",
                    "akzeptanzkriterien",
                    "user story",
                    "user stories",
                    "persona",
                    "stakeholder",
                    "scope",
                    "backlog",
                    "produkt",
                    "anforderung",
                    "anforderungen",
                ]
            ),
        )
    )

    # QA / Tests (EN + DE)
    rules.append(
        (
            "qa",
            pat(
                [
                    "test",
                    "tests",
                    "testing",
                    "pytest",
                    "unittest",
                    "integration",
                    "e2e",
                    "end-to-end",
                    "akzeptanz",
                    "acceptance",
                    "qa",
                    "quality",
                ]
            ),
        )
    )
    # Performance / Observability / Security scans grouped under telemetry queue (EN + DE)
    rules.append(
        (
            "telemetry",
            pat(
                [
                    "performance",
                    "latency",
                    "p95",
                    "p99",
                    "throughput",
                    "locust",
                    "benchmark",
                    "profiling",
                    "observability",
                    "monitoring",
                    "grafana",
                    "prometheus",
                    "load",
                    "loadtest",
                    "lasttest",
                    "leistung",
                    "latenz",
                    "durchsatz",
                    "telemetry",
                ]
            ),
        )
    )
    rules.append(
        (
            "telemetry",
            pat(
                [
                    "security",
                    "secure",
                    "bandit",
                    "owasp",
                    "xss",
                    "sqli",
                    "cve",
                    "pip-audit",
                    "dependency scan",
                    "sicherheit",
                    "penetration",
                    "pentest",
                ]
            ),
        )
    )

    # Repo / Scaffolding / DevOps
    rules.append(
        (
            "repo",
            pat(
                [
                    "scaffold",
                    "bootstrap",
                    "repo",
                    "repository",
                    "monorepo",
                    "init",
                    "initialize",
                    "setup",
                    "readme",
                    "dockerfile",
                    "docker-compose",
                    "compose",
                    "eslint",
                    "prettier",
                    "ci",
                    "cd",
                    "pipeline",
                ]
            ),
        )
    )

    # Architecture / Blueprint
    rules.append(
        (
            "architect",
            pat(
                [
                    "architecture",
                    "architectural",
                    "blueprint",
                    "diagram",
                    "adr",
                    "entscheidungs",
                    "architektur",
                    "high-level design",
                    "solution design",
                ]
            ),
        )
    )

    # Code Review
    rules.append(
        (
            "qa_review",
            pat(
                [
                    "code review",
                    "review code",
                    "static analysis",
                    "lint",
                    "linter",
                    "style check",
                    "clean code",
                    "codereview",
                ]
            ),
        )
    )

    # Refactor
    rules.append(
        (
            "qa_refactor",
            pat(["refactor", "refactoring", "cleanup", "aufräumen", "umstrukturieren"]),
        )
    )

    return rules


_RULES = _build_rules()


def heuristic_role(text: str) -> Optional[str]:
    """
    Return a canonical role based on simple keyword heuristics, or None if no match.
    We also honor explicit 'agent.*' hints to minimize ambiguity.
    """
    t = (text or "").lower()
    if not t:
        return None

    # Explicit agent hints first (strong signal)
    if "agent.e2e" in t or "integration test" in t or "end-to-end" in t:
        return "qa"
    if "agent.performance" in t or "locust" in t or "p95" in t:
        return "telemetry"
    if "agent.security" in t or "bandit" in t or "pip-audit" in t or "owasp" in t:
        return "telemetry"
    if "architecture & domain review" in t or "domain review" in t:
        return "reviewer"
    if "architecture review" in t and "domain" in t:
        return "reviewer"

    # Keyword rules (first match wins)
    for role, rx in _RULES:
        if rx.search(t):
            return role
    return None


def normalize_role(s: str) -> Optional[str]:
    """
    Map model outputs/synonyms to canonical roles used by the router.
    If the normalized role is unknown, return None so the caller can fallback.
    """
    if not s:
        return None
    u = s.strip().lower()
    mapping: Dict[str, str] = {
        # UX/UI
        "frontend": "ux_ui",
        "ui": "ux_ui",
        "ux": "ux_ui",
        "ui/ux": "ux_ui",
        "ux-ui": "ux_ui",
        "design": "ux_ui",
        "uiux": "ux_ui",
        # QA
        "qa": "qa",
        "testing": "qa",
        "test": "qa",
        "quality": "qa",
        "e2e": "qa",
        "integration": "qa",
        "acceptance": "qa",
        # Telemetry / Perf / Security
        "perf": "telemetry",
        "performance": "telemetry",
        "observability": "telemetry",
        "monitoring": "telemetry",
        "telemetry": "telemetry",
        "security": "telemetry",
        "sec": "telemetry",
        # Repo / DevOps
        "repo": "repo",
        "scaffold": "repo",
        "bootstrap": "repo",
        "devops": "repo",
        # Architecture
        "arch": "architect",
        "architecture": "architect",
        "architect": "architect",
        # Product / Requirements
        "po": "product",
        "product": "product",
        "requirements": "product",
        "prd": "product",
        # Review / Refactor
        "review": "qa_review",
        "code review": "qa_review",
        "static analysis": "qa_review",
        "lint": "qa_review",
        "refactor": "qa_refactor",
        "refactoring": "qa_refactor",
        "cleanup": "qa_refactor",
        "architecture & domain review": "reviewer",
        "domain review": "reviewer",
        "architecture review": "reviewer",
        "reviewer": "reviewer",
        # Default
        "developer": "dev",
        "development": "dev",
        "dev": "dev",
    }
    # Exact or mapped
    if u in mapping:
        return mapping[u]
    return u if u in CANONICAL_ROLES else None
