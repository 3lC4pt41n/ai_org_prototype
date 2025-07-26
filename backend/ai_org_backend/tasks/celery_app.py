"""Celery application instance for ai_org_backend tasks."""

from celery import Celery
from dotenv import load_dotenv
from ai_org_backend import config

# Load environment variables so configuration values are available when the
# module is imported by the Celery command line interface.
load_dotenv()


celery = Celery(__name__, broker=config.REDIS_URL, backend=config.REDIS_URL)
celery.conf.task_acks_late = True

