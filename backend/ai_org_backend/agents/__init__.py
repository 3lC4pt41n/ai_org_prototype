# Register the repo_composer agent so that Celery can discover it
from ai_org_backend.agents import repo_composer  # Importing ensures agent.repo task is registered
