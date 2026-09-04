import httpx
import respx
from sqlalchemy import select

from app.models.job import Job as JobModel
from app.services.discovery.greenhouse import discover_greenhouse_jobs

FAKE_RESPONSE = {
    "jobs": [
        {"id": 1, "title": "Engineer", "absolute_url": "https://x.test/1", "location": {"name": "Remote"}},
        {"id": 2, "title": "Designer", "absolute_url": "https://x.test/2", "location": {"name": "NYC"}},
    ]
}


@respx.mock
async def test_discover_greenhouse_jobs_is_safe_to_run_twice(db) -> None:
    respx.get("https://boards-api.greenhouse.io/v1/boards/acme/jobs").mock(
        return_value=httpx.Response(200, json=FAKE_RESPONSE)
    )

    await discover_greenhouse_jobs("acme", db)
    await discover_greenhouse_jobs("acme", db)

    result = await db.execute(select(JobModel).where(JobModel.company == "acme"))
    rows = result.scalars().all()

    assert len(rows) == 2