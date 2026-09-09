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