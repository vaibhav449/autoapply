import httpx
import respx
from sqlalchemy import select

from app.models.job import Job as JobModel
from app.services.discovery.adzuna import discover_adzuna_jobs

FAKE_RESPONSE = {
    "results": [
        {
            "id": 1,
            "title": "Engineer",
            "company": {"display_name": "Acme"},
            "location": {"display_name": "Bangalore"},
            "redirect_url": "https://x.test/1",
        },
        {
            "id": 2,
            "title": "Designer",
            "company": {"display_name": "Acme"},
            "location": {"display_name": "Pune"},
            "redirect_url": "https://x.test/2",
        },
    ]
}


@respx.mock
async def test_discover_adzuna_jobs_is_safe_to_run_twice(db) -> None:
    respx.get("https://api.adzuna.com/v1/api/jobs/in/search/1").mock(
        return_value=httpx.Response(200, json=FAKE_RESPONSE)
    )

    await discover_adzuna_jobs("engineer", "Bangalore", "in", db)
    await discover_adzuna_jobs("engineer", "Bangalore", "in", db)

    result = await db.execute(select(JobModel).where(JobModel.source == "adzuna"))
    rows = result.scalars().all()

    assert len(rows) == 2
