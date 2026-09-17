import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.schemas.job import Job
from app.services.discovery import clean_html_description, save_jobs


async def fetch_adzuna_jobs(
    query: str,
    location: str = "",
    country: str = "in",
    results_per_page: int = 20,
    what_exclude: str = "",
) -> list[Job]:
    url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
    params: dict[str, str | int] = {
        "app_id": settings.adzuna_app_id,
        "app_key": settings.adzuna_app_key,
        "results_per_page": results_per_page,
        "what": query,
        "content-type": "application/json",
    }
    if location:
        params["where"] = location
    # Keeps roles above the candidate's level out of the pool entirely. Measured
    # on a real query: senior-sounding titles fell from 12/20 to 0/20.
    if what_exclude:
        params["what_exclude"] = what_exclude

    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

    jobs = []
    for result in data["results"]:
        company_name = (result.get("company") or {}).get("display_name") or "Unknown company"
        jobs.append(
            Job(
                external_id=str(result["id"]),
                source="adzuna",
                title=result["title"],
                company=company_name,
                location=(result.get("location") or {}).get("display_name"),
                url=result["redirect_url"],
                description=clean_html_description(result.get("description")),
            )
        )
    return jobs


async def discover_adzuna_jobs(
    query: str,
    location: str,
    country: str,
    db: AsyncSession,
    what_exclude: str = "",
) -> list[Job]:
    """Search Adzuna for a keyword/location query and upsert results into the shared jobs pool."""
    jobs = await fetch_adzuna_jobs(query, location, country, what_exclude=what_exclude)
    await save_jobs(jobs, db)
    return jobs
