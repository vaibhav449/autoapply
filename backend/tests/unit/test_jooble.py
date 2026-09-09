import httpx
import respx

from app.core.config import settings
from app.services.discovery.jooble import fetch_jooble_jobs

FAKE_JOOBLE_RESPONSE = {
    "totalCount": 2,
    "jobs": [
        {
            "id": 111,
            "title": "Backend Engineer",
            "location": "Bangalore, India",
            "company": "Acme Corp",
            "link": "https://jooble.org/jobs/111",
        },
        {
            "id": 222,
            "title": "Designer",
            "link": "https://jooble.org/jobs/222",
        },
    ],
}


@respx.mock
async def test_fetch_jooble_jobs_maps_fields_correctly() -> None:
    respx.post(f"https://jooble.org/api/{settings.jooble_api_key}").mock(
        return_value=httpx.Response(200, json=FAKE_JOOBLE_RESPONSE)
    )

    jobs = await fetch_jooble_jobs("backend engineer", "Bangalore")

    assert len(jobs) == 2

    assert jobs[0].external_id == "111"
    assert jobs[0].source == "jooble"
    assert jobs[0].title == "Backend Engineer"
    assert jobs[0].company == "Acme Corp"
    assert jobs[0].location == "Bangalore, India"
    assert str(jobs[0].url) == "https://jooble.org/jobs/111"

    # second job has no "company" or "location" key at all — must not crash
    assert jobs[1].company == "Unknown company"
    assert jobs[1].location is None
