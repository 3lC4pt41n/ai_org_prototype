DEFAULT_QUEUES = ['dev', 'qa', 'ux_ui', 'telemetry', 'architect', 'insight']
ROUTES = {
    'ai_org_backend.tasks.llm_tasks.insight_agent': {'queue': 'insight'},
}
