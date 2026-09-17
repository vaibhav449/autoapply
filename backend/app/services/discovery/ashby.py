import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.job import Job
from app.services.discovery import reconcile_board_sweep, save_jobs


async def fetch_ashby_jobs(company_slug: str) -> list[Job]:
    # One request returns the whole board including descriptionPlain, so unlike
    # SmartRecruiters there is no per-posting detail fetch.
    url = f"https://api.ashbyhq.com/posting-api/job-board/{company_slug}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()

    return [
        Job(
            external_id=str(job["id"]),
            source="ashby",
            title=job["title"],
            company=company_slug,
            location=job.get("location"),
            url=job["jobUrl"],
            description=job.get("descriptionPlain"),
        )
        for job in data.get("jobs", [])
        # Unlisted postings are drafts or internal-only; they are not applyable.
        if job.get("isListed", True)
    ]


async def discover_ashby_jobs(company_slug: str, db: AsyncSession) -> list[Job]:
    """Fetch a company's Ashby board and upsert it into the shared jobs pool."""
    jobs = await fetch_ashby_jobs(company_slug)
    await save_jobs(jobs, db)
    await reconcile_board_sweep("ashby", company_slug, db)
    return jobs
