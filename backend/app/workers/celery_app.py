from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "autoapply",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    beat_schedule={
        "poll-greenhouse-every-hour": {
            "task": "discovery.poll_greenhouse",
            "schedule": 3600.0,
        },
        "poll-lever-every-hour": {
            "task": "discovery.poll_lever",
            "schedule": 3600.0,
        },
    },
)
