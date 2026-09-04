import asyncio

from app.db.session import async_session, engine
from app.services.discovery.greenhouse import discover_greenhouse_jobs
from app.services.discovery.lever import discover_lever_jobs
from app.workers.celery_app import celery_app

GREENHOUSE_COMPANIES = ["stripe"]
LEVER_COMPANIES = ["palantir"]


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
