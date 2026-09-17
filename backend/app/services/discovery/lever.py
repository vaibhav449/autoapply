import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.job import Job
from app.services.discovery import reconcile_board_sweep, save_jobs


async def fetch_lever_jobs(company_slug: str) -> list[Job]:
    url = f"https://api.lever.co/v0/postings/{company_slug}?mode=json"

    # httpx's default 5s timeout isn't enough now that responses include full
    # descriptions for every posting (Palantir's is several MB of text).
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()

    return [
        Job(
            external_id=posting["id"],
            source="lever",
            title=posting["text"],
            company=company_slug,
            location=posting.get("categories", {}).get("location"),
            url=posting["hostedUrl"],
            description=posting.get("descriptionPlain"),
        )
        for posting in data
    ]


async def discover_lever_jobs(company_slug: str, db: AsyncSession) -> list[Job]:
    """Fetch a company's Lever postings and upsert them into the shared jobs pool."""
    jobs = await fetch_lever_jobs(company_slug)
    await save_jobs(jobs, db)
    await reconcile_board_sweep("lever", company_slug, db)
    return jobs