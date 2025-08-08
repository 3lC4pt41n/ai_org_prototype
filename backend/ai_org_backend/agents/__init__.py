"""Agent package initialisation.

Importing repo_composer registers the Celery task when available. During
lightweight test runs we ignore missing optional dependencies so the
planner can be imported in isolation.
"""

try:
    # Importing ensures agent.repo task is registered when Celery is configured
    from ai_org_backend.agents import repo_composer  # noqa: F401
except Exception:  # pragma: no cover - optional dependency may be missing  # nosec B110
    pass
