import httpx
import respx

from app.services.discovery.adzuna import fetch_adzuna_jobs

FAKE_ADZUNA_RESPONSE = {
    "results": [
        {
            "id": 111,
            "title": "Backend Engineer",
            "company": {"display_name": "Acme Corp"},
            "location": {"display_name": "Bangalore, India"},
            "redirect_url": "https://www.adzuna.in/jobs/details/111",
        },
        {
            "id": 222,
            "title": "Designer",
            "company": {"display_name": ""},
            "redirect_url": "https://www.adzuna.in/jobs/details/222",
        },
    ]
}


@respx.mock
async def test_fetch_adzuna_jobs_maps_fields_correctly() -> None:
    respx.get("https://api.adzuna.com/v1/api/jobs/in/search/1").mock(
        return_value=httpx.Response(200, json=FAKE_ADZUNA_RESPONSE)
    )

    jobs = await fetch_adzuna_jobs("backend engineer", "Bangalore", "in")

    assert len(jobs) == 2

    assert jobs[0].external_id == "111"
    assert jobs[0].source == "adzuna"
    assert jobs[0].title == "Backend Engineer"
    assert jobs[0].company == "Acme Corp"
    assert jobs[0].location == "Bangalore, India"
    assert str(jobs[0].url) == "https://www.adzuna.in/jobs/details/111"

    # second job has blank company display_name and no "location" key at all —
    # must not crash, company must fall back to placeholder, location must be None
    assert jobs[1].company == "Unknown company"
    assert jobs[1].location is None
