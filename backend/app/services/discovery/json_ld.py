import json

import httpx
from bs4 import BeautifulSoup

from app.schemas.job import Job
from app.services.discovery import clean_html_description


async def fetch_json_ld_jobs(url: str) -> list[Job]:
    """Look for schema.org JobPosting structured data on an arbitrary page."""
    async with httpx.AsyncClient(follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        html = response.text

    soup = BeautifulSoup(html, "lxml")
    jobs: list[Job] = []

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except json.JSONDecodeError:
            continue

        entries = data if isinstance(data, list) else [data]
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("@type") != "JobPosting":
                continue
            try:
                jobs.append(_job_posting_to_job(entry, url))
            except (KeyError, TypeError):
                continue

    return jobs


def _job_posting_to_job(posting: dict, page_url: str) -> Job:
    org = posting.get("hiringOrganization")
    company = org.get("name") if isinstance(org, dict) else None
    if not company:
        company = httpx.URL(page_url).host

    location = None
    job_location = posting.get("jobLocation")
    if isinstance(job_location, list):
        job_location = job_location[0] if job_location else None
    if isinstance(job_location, dict):
        address = job_location.get("address")
        if isinstance(address, dict):
            location = address.get("addressLocality")

    identifier = posting.get("identifier")
    external_id = page_url
    if isinstance(identifier, dict) and identifier.get("value"):
        external_id = str(identifier["value"])

    return Job(
        external_id=external_id,
        source="json-ld",
        title=posting["title"],
        company=company,
        location=location,
        url=page_url,
        description=clean_html_description(posting.get("description")),
    )
