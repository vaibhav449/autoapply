import httpx
import respx
from sqlalchemy import select

from app.core.config import settings
from app.models.job import Job as JobModel
from app.services.discovery.jooble import discover_jooble_jobs

FAKE_RESPONSE = {
    "totalCount": 2,
    "jobs": [
        {"id": 1, "title": "Engineer", "company": "Acme", "location": "Bangalore", "link": "https://x.test/1"},
        {"id": 2, "title": "Designer", "company": "Acme", "location": "Pune", "link": "https://x.test/2"},
    ],
}


@respx.mock
async def test_discover_jooble_jobs_is_safe_to_run_twice(db) -> None:
    respx.post(f"https://jooble.org/api/{settings.jooble_api_key}").mock(
        return_value=httpx.Response(200, json=FAKE_RESPONSE)
    )

    await discover_jooble_jobs("engineer", "Bangalore", db)
    await discover_jooble_jobs("engineer", "Bangalore", db)

    result = await db.execute(select(JobModel).where(JobModel.source == "jooble"))
    rows = result.scalars().all()

    assert len(rows) == 2
