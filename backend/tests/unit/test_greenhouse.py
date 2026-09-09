import httpx
import respx

from app.services.discovery.greenhouse import fetch_greenhouse_jobs

FAKE_GREENHOUSE_RESPONSE = {
    "jobs": [
        {
            "id": 111,
            "title": "Backend Engineer",
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/111",
            "location": {"name": "Remote"},
            "content": "&lt;p&gt;Requires &lt;strong&gt;3+ years&lt;/strong&gt; of experience.&lt;/p&gt;",
        },
        {
            "id": 222,
            "title": "Designer",
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/222",
        },
    ]
}


@respx.mock
async def test_fetch_greenhouse_jobs_maps_fields_correctly() -> None:
    respx.get("https://boards-api.greenhouse.io/v1/boards/totally-fake-co/jobs").mock(
        return_value=httpx.Response(200, json=FAKE_GREENHOUSE_RESPONSE)
    )

    jobs = await fetch_greenhouse_jobs("totally-fake-co")

    assert len(jobs) == 2

    assert jobs[0].external_id == "111"
    assert jobs[0].source == "greenhouse"
    assert jobs[0].title == "Backend Engineer"
    assert jobs[0].company == "totally-fake-co"
    assert jobs[0].location == "Remote"
    assert str(jobs[0].url) == "https://boards.greenhouse.io/acme/jobs/111"
    # HTML-escaped entities and tags must be cleaned into plain text
    assert jobs[0].description == "Requires 3+ years of experience."

    # second job has no "location" key at all — must not crash, must come out as None
    assert jobs[1].location is None
    # second job has no "content" key at all — must not crash, must come out as None
    assert jobs[1].description is None