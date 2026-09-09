import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.schemas.job import Job
from app.services.discovery import save_jobs


async def fetch_jooble_jobs(keywords: str, location: str = "") -> list[Job]:
    url = f"https://jooble.org/api/{settings.jooble_api_key}"
    payload = {"keywords": keywords, "location": location}

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()

    return [
        Job(
            external_id=str(job["id"]),
            source="jooble",
            title=job["title"],
            company=job.get("company") or "Unknown company",
            location=job.get("location"),
            url=job["link"],
            description=job.get("snippet"),
        )
        for job in data.get("jobs", [])
    ]


async def discover_jooble_jobs(keywords: str, location: str, db: AsyncSession) -> list[Job]:
    """Search Jooble for a keyword/location query and upsert results into the shared jobs pool.

    Jooble's free tier is a lifetime cap of 500 requests, not a recurring monthly quota —
    this must only be invoked manually (via /discover/jooble or a manual Celery task call),
    never from the recurring beat schedule.
    """
    jobs = await fetch_jooble_jobs(keywords, location)
    await save_jobs(jobs, db)
    return jobs
