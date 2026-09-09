import asyncio

from app.db.session import async_session, engine
from app.services.discovery.adzuna import discover_adzuna_jobs
from app.services.discovery.greenhouse import discover_greenhouse_jobs
from app.services.discovery.jooble import discover_jooble_jobs
from app.services.discovery.lever import discover_lever_jobs
from app.workers.celery_app import celery_app

GREENHOUSE_COMPANIES = ["stripe"]
LEVER_COMPANIES = ["palantir"]

# India-focused tech role clusters. Kept to 15 entries so a once-daily poll (see
# celery_app.py's beat_schedule) uses only 15 of Adzuna's ~33/day free-tier budget,
# leaving headroom for manual /discover/adzuna calls during the same day.
ADZUNA_QUERY_CLUSTERS = [
    ("backend engineer", "Bangalore"),
    ("backend engineer", "remote"),
    ("frontend engineer", "Bangalore"),
    ("full stack developer", "Hyderabad"),
    ("software engineer", "Pune"),
    ("data engineer", "Bangalore"),
    ("data scientist", "India"),
    ("devops engineer", "India"),
    ("machine learning engineer", "Bangalore"),
    ("python developer", "remote"),
    ("java developer", "Chennai"),
    ("mobile developer", "Bangalore"),
    ("QA engineer", "Pune"),
    ("site reliability engineer", "India"),
    ("product manager", "Bangalore"),
]


@celery_app.task(name="discovery.poll_greenhouse")
def poll_greenhouse() -> None:
    asyncio.run(_poll_greenhouse())


async def _poll_greenhouse() -> None:
    try:
        async with async_session() as db:
            for company in GREENHOUSE_COMPANIES:
                await discover_greenhouse_jobs(company, db)
    finally:
        await engine.dispose()


@celery_app.task(name="discovery.poll_lever")
def poll_lever() -> None:
    asyncio.run(_poll_lever())


async def _poll_lever() -> None:
    try:
        async with async_session() as db:
            for company in LEVER_COMPANIES:
                await discover_lever_jobs(company, db)
    finally:
        await engine.dispose()


@celery_app.task(name="discovery.poll_adzuna")
def poll_adzuna() -> None:
    asyncio.run(_poll_adzuna())


async def _poll_adzuna() -> None:
    try:
        async with async_session() as db:
            for query, location in ADZUNA_QUERY_CLUSTERS:
                await discover_adzuna_jobs(query, location, "in", db)
    finally:
        await engine.dispose()


# poll_jooble is deliberately NOT on the beat schedule (see celery_app.py) — Jooble's
# free tier is a lifetime cap of 500 total requests, not a recurring monthly quota, so
# it only ever runs on manual invocation, one query/location pair at a time.
@celery_app.task(name="discovery.poll_jooble")
def poll_jooble(query: str = "software engineer", location: str = "India") -> None:
    asyncio.run(_poll_jooble(query, location))


async def _poll_jooble(query: str, location: str) -> None:
    try:
        async with async_session() as db:
            await discover_jooble_jobs(query, location, db)
    finally:
        await engine.dispose()
