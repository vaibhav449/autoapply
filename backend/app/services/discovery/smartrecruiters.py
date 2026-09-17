import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job as JobModel
from app.schemas.job import Job
from app.services.discovery import clean_html_description, reconcile_board_sweep, save_jobs

API_ROOT = "https://api.smartrecruiters.com/v1/companies"
PAGE_SIZE = 100

# Order matters — this is how the ad reads on the posting page.
AD_SECTIONS = ("companyDescription", "jobDescription", "qualifications", "additionalInformation")


def posting_url(company_slug: str, posting_id: str) -> str:
    """The public posting page. Built rather than read from the detail response so
    that listing-only passes still produce a usable link.
    """
    return f"https://jobs.smartrecruiters.com/{company_slug}/{posting_id}"


def _location(raw: dict | None) -> str | None:
    if not raw:
        return None
    country = (raw.get("country") or "").upper() or None
    parts = [raw.get("city"), raw.get("region"), country]
    return ", ".join(part for part in parts if part) or None


def _description(job_ad: dict | None) -> str | None:
    sections = (job_ad or {}).get("sections") or {}
    texts = [clean_html_description((sections.get(name) or {}).get("text")) for name in AD_SECTIONS]
    return "\n\n".join(text for text in texts if text) or None


async def fetch_smartrecruiters_postings(company_slug: str) -> list[dict]:
    """Every posting for a company, following pagination to the end — the board is
    only an exhaustive signal for closure detection if we actually read all of it.
    """
    postings: list[dict] = []
    offset = 0

    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            response = await client.get(
                f"{API_ROOT}/{company_slug}/postings",
                params={"limit": PAGE_SIZE, "offset": offset},
            )
            response.raise_for_status()
            payload = response.json()

            page = payload.get("content") or []
            postings.extend(page)
            offset += len(page)
            if not page or offset >= payload.get("totalFound", 0):
                return postings


async def fetch_posting_description(client: httpx.AsyncClient, slug: str, pid: str) -> str | None:
    response = await client.get(f"{API_ROOT}/{slug}/postings/{pid}")
    if response.status_code != 200:
        return None
    return _description(response.json().get("jobAd"))


async def _known_external_ids(company_slug: str, db: AsyncSession) -> set[str]:
    result = await db.execute(
        select(JobModel.external_id).where(
            JobModel.source == "smartrecruiters", JobModel.company == company_slug
        )
    )
    return set(result.scalars().all())


async def discover_smartrecruiters_jobs(company_slug: str, db: AsyncSession) -> list[Job]:
    """Fetch a company's SmartRecruiters board and upsert it into the shared pool.

    Descriptions need a request per posting, so they are only fetched for postings
    we have never seen. Ones we already hold are still returned, so save_jobs
    stamps last_seen_at and the board stays a complete sweep for closure detection.
    """
    postings = await fetch_smartrecruiters_postings(company_slug)
    known = await _known_external_ids(company_slug, db)

    jobs: list[Job] = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for posting in postings:
            posting_id = str(posting["id"])
            description = (
                None
                if posting_id in known
                else await fetch_posting_description(client, company_slug, posting_id)
            )
            jobs.append(
                Job(
                    external_id=posting_id,
                    source="smartrecruiters",
                    title=posting["name"],
                    company=company_slug,
                    location=_location(posting.get("location")),
                    url=posting_url(company_slug, posting_id),
                    description=description,
                )
            )

    await save_jobs(jobs, db)
    await reconcile_board_sweep("smartrecruiters", company_slug, db)
    return jobs
