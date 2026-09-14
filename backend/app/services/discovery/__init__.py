import html

from bs4 import BeautifulSoup
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job as JobModel
from app.schemas.job import Job


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
        stmt = pg_insert(JobModel).values(rows).on_conflict_do_nothing(
            index_elements=["source", "external_id"]
        )
        await db.execute(stmt)
        await db.commit()


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