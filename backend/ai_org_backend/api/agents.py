from fastapi import APIRouter
from celery import Celery
import os

REDIS_URL = os.getenv("REDIS_URL", "redis://:ai_redis_pw@localhost:6379/0")
celery_app = Celery(__name__, broker=REDIS_URL, backend=REDIS_URL)

router = APIRouter(prefix='/api/agent', tags=['agents'])


@router.get('/{queue}/ping')
def ping(queue: str):
    insp = celery_app.control.inspect()
    active = insp.active_queues() or {}
    return {
        'alive': queue in active.keys(),
        'tasks': active.get(queue, [])
    }
