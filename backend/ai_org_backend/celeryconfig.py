"""Celery configuration with task timeouts and resilience settings."""

# ── Default Queues ──
DEFAULT_QUEUES = ["dev", "qa", "ux_ui", "telemetry", "architect", "insight"]

ROUTES = {
    "ai_org_backend.agents.architect.*": {"queue": "architect"},
    "ai_org_backend.agents.dev.*": {"queue": "dev"},
    "ai_org_backend.tasks.llm_tasks.insight_agent": {"queue": "insight"},
}

# ── S1-07: Global Task Timeouts ──
# soft_time_limit raises SoftTimeLimitExceeded inside the task (allows cleanup)
# time_limit hard-kills the worker process after this many seconds
TASK_SOFT_TIME_LIMIT = 300  # 5 minutes
TASK_TIME_LIMIT = 600  # 10 minutes

# ── S1-08: Role-specific Timeouts ──
# Override per-task via @shared_task(soft_time_limit=..., time_limit=...)
ROLE_TIMEOUTS = {
    "planner": {"soft": 900, "hard": 1200},      # 15min/20min - complex planning
    "repo_composer": {"soft": 900, "hard": 1200}, # 15min/20min - large repos
    "architect": {"soft": 600, "hard": 900},      # 10min/15min
    "reviewer": {"soft": 600, "hard": 900},       # 10min/15min
    "dev": {"soft": 300, "hard": 600},             # 5min/10min (default)
    "qa": {"soft": 300, "hard": 600},              # 5min/10min
    "ux_ui": {"soft": 300, "hard": 600},           # 5min/10min
    "vision": {"soft": 300, "hard": 600},          # 5min/10min
    "product_owner": {"soft": 300, "hard": 600},   # 5min/10min
    "insight": {"soft": 180, "hard": 300},         # 3min/5min
}


def get_timeout_for_role(role: str) -> dict:
    """Return soft/hard timeout dict for a given agent role."""
    return ROLE_TIMEOUTS.get(role, {"soft": TASK_SOFT_TIME_LIMIT, "hard": TASK_TIME_LIMIT})


# ── S3-14: Celery Beat schedule for periodic graph reconciliation ──
CELERY_BEAT_SCHEDULE = {
    "graph-reconcile-every-30min": {
        "task": "graph.reconcile",
        "schedule": 1800.0,  # every 30 minutes
    },
    # S-Sprint3 Fix #11: Stuck-task watchdog runs every 5 minutes
    "watchdog-stuck-tasks": {
        "task": "watchdog.detect_stuck_tasks",
        "schedule": 300.0,  # every 5 minutes
    },
}
