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
        # Adzuna's free tier is ~1,000 calls/month (~33/day). ADZUNA_QUERY_CLUSTERS has
        # 15 entries, so polling once/day (not hourly, unlike Greenhouse/Lever above)
        # uses 15 calls/day — well within budget with headroom for manual queries.
        "poll-adzuna-once-daily": {
            "task": "discovery.poll_adzuna",
            "schedule": 86400.0,
        },
        # poll_jooble is intentionally NOT scheduled here. Jooble's free tier is a
        # LIFETIME cap of 500 total requests (not monthly/recurring) — any automatic
        # recurring schedule would silently and irreversibly drain that quota. Trigger
        # discover_jooble_jobs only on demand via GET /discover/jooble, or by manually
        # invoking the discovery.poll_jooble Celery task.
    },
)
