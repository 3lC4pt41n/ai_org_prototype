DEFAULT_QUEUES = ["dev", "qa", "ux_ui", "telemetry", "architect", "insight"]

ROUTES = {
    # architect & dev waren schon da
    "ai_org_backend.agents.architect.*": {"queue": "architect"},
    "ai_org_backend.agents.dev.*":       {"queue": "dev"},
    # insight‑Task sauber routen
    "ai_org_backend.tasks.llm_tasks.insight_agent": {"queue": "insight"},
}
