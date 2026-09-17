import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.profile import Profile
from app.services.discovery.adzuna import discover_adzuna_jobs
from app.services.discovery.board_discovery import discover_boards_from_aggregators
from app.services.discovery.boards import poll_active_boards
from app.services.discovery.jooble import discover_jooble_jobs
from app.services.discovery.queries import build_adzuna_queries
from app.services.scoring.embeddings import embed_unembedded_jobs
from app.services.scoring.requirements import extract_missing_requirements
from app.workers.celery_app import celery_app

# One Adzuna call per query, against a free tier of roughly 33/day. The rest of
# the budget stays free for manual /discover/adzuna calls.
ADZUNA_DAILY_BUDGET = 18


@asynccontextmanager
async def task_session() -> AsyncIterator[AsyncSession]:
    """A session on an engine built inside THIS task's event loop.

    Celery runs every task through a fresh asyncio.run(), but an engine's pool
    binds to the first loop that touches it — so sharing app.db.session's
    module-level engine here works for one task per worker process and then fails
    with "Event loop is closed" on the next one.
    """
    engine = create_async_engine(settings.database_url)
    try:
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as session:
            yield session
    finally:
        await engine.dispose()


@celery_app.task(name="discovery.poll_ats_boards")
def poll_ats_boards() -> None:
    """Polls every board in the ats_boards table — Greenhouse, Lever, Ashby and
    SmartRecruiters alike. Replaces the per-source tasks that read hardcoded
    company lists; adding a company is now a row, not a deploy.
    """
    asyncio.run(_poll_ats_boards())


async def _poll_ats_boards() -> None:
    async with task_session() as db:
        await poll_active_boards(db)


@celery_app.task(name="discovery.discover_ats_boards")
def discover_ats_boards() -> None:
    """Turn aggregator company names into readable ATS boards. This is the payoff
    from Adzuna: it is poor at descriptions but good at revealing who is hiring,
    and a board found once yields full text and liveness for every future job.
    """
    asyncio.run(_discover_ats_boards())


async def _discover_ats_boards() -> None:
    async with task_session() as db:
        await discover_boards_from_aggregators(db)


@celery_app.task(name="discovery.poll_adzuna")
def poll_adzuna() -> None:
    asyncio.run(_poll_adzuna())


async def _poll_adzuna() -> None:
    async with task_session() as db:
        # Queries are generated from what our profiles are actually looking for.
        # A fixed senior-blind cluster list is how the pool filled up with 6-to-10
        # year roles for a candidate with one year.
        levels = {
            level
            for (level,) in (await db.execute(select(Profile.target_level))).all()
            if level is not None
        }
        for query in build_adzuna_queries(levels, budget=ADZUNA_DAILY_BUDGET):
            await discover_adzuna_jobs(
                query.what, query.where, "in", db, what_exclude=query.what_exclude
            )


# poll_jooble is deliberately NOT on the beat schedule (see celery_app.py) — Jooble's
# free tier is a lifetime cap of 500 total requests, not a recurring monthly quota, so
# it only ever runs on manual invocation, one query/location pair at a time.
@celery_app.task(name="discovery.poll_jooble")
def poll_jooble(query: str = "software engineer", location: str = "India") -> None:
    asyncio.run(_poll_jooble(query, location))


async def _poll_jooble(query: str, location: str) -> None:
    async with task_session() as db:
        await discover_jooble_jobs(query, location, db)


@celery_app.task(name="scoring.embed_unembedded_jobs")
def embed_unembedded_jobs_task() -> None:
    asyncio.run(_embed_unembedded_jobs())


async def _embed_unembedded_jobs() -> None:
    async with task_session() as db:
        await embed_unembedded_jobs(db)


@celery_app.task(name="scoring.extract_missing_requirements")
def extract_missing_requirements_task() -> None:
    """Annotate the whole pool, not just whatever a ranking request happened to
    look at. Without this, 98% of jobs were never read and could never match.
    """
    asyncio.run(_extract_missing_requirements())


async def _extract_missing_requirements() -> None:
    async with task_session() as db:
        await extract_missing_requirements(db)
