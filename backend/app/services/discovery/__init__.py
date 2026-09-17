import html

from bs4 import BeautifulSoup
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job as JobModel
from app.schemas.job import Job

# Sources that return a company's ENTIRE board in one unpaginated response, so a
# job's absence is real evidence it closed. Adzuna and Jooble are keyword searches
# — absence there only means "didn't match today's query" and must never expire.
EXHAUSTIVE_SOURCES = frozenset({"greenhouse", "lever", "ashby", "smartrecruiters"})

MISSED_SWEEPS_BEFORE_CLOSED = 2


def clean_html_description(raw: str | None) -> str | None:
    """Strip HTML/entities from a source's raw description into plain text."""
    if not raw:
        return None
    return BeautifulSoup(html.unescape(raw), "lxml").get_text(" ", strip=True)


async def save_jobs(jobs: list[Job], db: AsyncSession) -> None:
    """Upsert normalized jobs from any source into the shared jobs pool."""
    rows = [
        {
            "external_id": job.external_id,
            "source": job.source,
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "url": str(job.url),
            "description": job.description,
        }
        for job in jobs
    ]

    if rows:
        stmt = pg_insert(JobModel).values(rows)
        # Only liveness columns are updated on conflict — title/description/url are
        # deliberately left alone, preserving the original never-clobber behaviour
        # (refresh_missing_descriptions is the one path allowed to touch content).
        # A job reappearing on a board is treated as reopened.
        stmt = stmt.on_conflict_do_update(
            index_elements=["source", "external_id"],
            set_={"last_seen_at": func.now(), "missed_sweeps": 0, "closed_at": None},
        )
        await db.execute(stmt)
        await db.commit()


async def reconcile_board_sweep(source: str, company: str, db: AsyncSession) -> int:
    """Close jobs that a complete board sweep no longer lists. Returns how many.

    Staleness is judged against the newest sighting among the board's OWN jobs
    rather than wall-clock time: if a poll fails, nothing is stamped, that maximum
    does not move, and nothing is expired. A clock-based rule would declare an
    entire board closed the first time the API timed out.
    """
    if source not in EXHAUSTIVE_SOURCES:
        return 0

    newest_sighting = await db.scalar(
        select(func.max(JobModel.last_seen_at)).where(
            JobModel.source == source, JobModel.company == company
        )
    )
    if newest_sighting is None:
        return 0

    board = (JobModel.source == source, JobModel.company == company)

    await db.execute(
        update(JobModel)
        .where(*board, JobModel.closed_at.is_(None), JobModel.last_seen_at < newest_sighting)
        .values(missed_sweeps=JobModel.missed_sweeps + 1)
    )
    closed = await db.execute(
        update(JobModel)
        .where(
            *board,
            JobModel.closed_at.is_(None),
            JobModel.missed_sweeps >= MISSED_SWEEPS_BEFORE_CLOSED,
        )
        .values(closed_at=func.now())
    )
    await db.commit()
    return closed.rowcount


async def refresh_missing_descriptions(jobs: list[Job], db: AsyncSession) -> None:
    """Repair utility, not part of the regular discovery flow: backfill description
    on existing rows where it's currently NULL. Unlike save_jobs' DO NOTHING, this
    explicitly updates existing rows — but only where description IS NULL, so it
    can never clobber real data, and is safe to re-run.
    """
    rows = [
        {
            "external_id": job.external_id,
            "source": job.source,
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "url": str(job.url),
            "description": job.description,
        }
        for job in jobs
    ]

    if rows:
        stmt = pg_insert(JobModel).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["source", "external_id"],
            set_={"description": stmt.excluded.description},
            where=JobModel.description.is_(None),
        )
        await db.execute(stmt)
        await db.commit()