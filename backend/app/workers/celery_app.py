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
        # One task for every ATS board in the ats_boards table. Boards are cheap to
        # poll (one request each, except SmartRecruiters' per-posting descriptions,
        # which are only fetched for postings we've never seen).
        "poll-ats-boards-every-hour": {
            "task": "discovery.poll_ats_boards",
            "schedule": 3600.0,
        },
        # Runs after the daily Adzuna poll has had a chance to surface new company
        # names. Only probes companies with no board on record, so it costs little
        # once the backlog is worked through.
        "discover-ats-boards-once-daily": {
            "task": "discovery.discover_ats_boards",
            "schedule": 86400.0,
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
        "embed-unembedded-jobs-every-15-min": {
            "task": "scoring.embed_unembedded_jobs",
            "schedule": 900.0,
        },
        # Requirements for the whole pool, not just whatever a ranking request
        # happened to look at. A job with no requirements on record can never be
        # matched, however well it fits — that left 98% of the pool invisible.
        "extract-missing-requirements-every-5-min": {
            "task": "scoring.extract_missing_requirements",
            "schedule": 300.0,
        },
    },
)
