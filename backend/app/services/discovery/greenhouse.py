import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.job import Job
from app.services.discovery import save_jobs


async def fetch_greenhouse_jobs(company_slug: str) -> list[Job]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{company_slug}/jobs"

    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()

    return [
        Job(
            external_id=str(job["id"]),
            source="greenhouse",
            title=job["title"],
            company=company_slug,
            location=job.get("location", {}).get("name"),
            url=job["absolute_url"],
        )
        for job in data["jobs"]
    ]


async def discover_greenhouse_jobs(company_slug: str, db: AsyncSession) -> list[Job]:
    """Fetch a company's Greenhouse postings and upsert them into the shared jobs pool."""
    jobs = await fetch_greenhouse_jobs(company_slug)
    await save_jobs(jobs, db)
    return jobs
