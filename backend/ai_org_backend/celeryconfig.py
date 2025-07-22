DEFAULT_QUEUES = ["dev", "qa", "ux_ui", "telemetry", "architect"]

ROUTES = {
    "ai_org_backend.agents.architect.*": {"queue": "architect"},
    "ai_org_backend.agents.dev.*": {"queue": "dev"},
}

