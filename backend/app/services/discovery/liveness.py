import enum

import httpx

from app.models.job import Job as JobModel


class Liveness(str, enum.Enum):
    OPEN = "open"
    CLOSED = "closed"
    UNVERIFIABLE = "unverifiable"


# Per-posting endpoints that answer 200 for a live job and 404 for a gone one,
# both verified against the live APIs before this was written.
SINGLE_JOB_ENDPOINTS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{company}/jobs/{external_id}",
    "lever": "https://api.lever.co/v0/postings/{company}/{external_id}",
}


async def check_job_liveness(job: JobModel) -> Liveness:
    """Ask the source whether a single posting is still open.

    Aggregator listings report UNVERIFIABLE rather than a guess: Adzuna's landing
    pages return 403 to plain HTTP and to a real headless browser alike, so there
    is no honest answer to give. A network failure is UNVERIFIABLE too — our own
    timeout is not evidence that an employer stopped hiring.
    """
    if job.closed_at is not None:
        return Liveness.CLOSED

    endpoint = SINGLE_JOB_ENDPOINTS.get(job.source)
    if endpoint is None:
        return Liveness.UNVERIFIABLE

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                endpoint.format(company=job.company, external_id=job.external_id)
            )
    except httpx.HTTPError:
        return Liveness.UNVERIFIABLE

    if response.status_code == 404:
        return Liveness.CLOSED
    if response.is_success:
        return Liveness.OPEN
    return Liveness.UNVERIFIABLE
