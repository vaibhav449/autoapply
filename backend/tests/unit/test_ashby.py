import httpx
import respx

from app.services.discovery.ashby import fetch_ashby_jobs

BOARD_URL = "https://api.ashbyhq.com/posting-api/job-board/totally-fake-co"

FAKE_RESPONSE = {
    "apiVersion": "1",
    "jobs": [
        {
            "id": "81a6c511-64f1-435e-9a5c-3ec2cf868e30",
            "title": "Backend Engineer",
            "location": "Bangalore HQ",
            "jobUrl": "https://jobs.ashbyhq.com/acme/81a6c511",
            "applyUrl": "https://jobs.ashbyhq.com/acme/81a6c511/application",
            "descriptionPlain": "Requires 3+ years of experience.",
            "isListed": True,
        },
        {
            "id": "no-location-or-description",
            "title": "Designer",
            "jobUrl": "https://jobs.ashbyhq.com/acme/222",
            "isListed": True,
        },
        {
            "id": "draft-posting",
            "title": "Not Published Yet",
            "jobUrl": "https://jobs.ashbyhq.com/acme/333",
            "isListed": False,
        },
    ],
}


@respx.mock
async def test_fetch_ashby_jobs_maps_fields_correctly() -> None:
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, json=FAKE_RESPONSE))

    jobs = await fetch_ashby_jobs("totally-fake-co")

    # the unlisted posting is dropped — drafts and internal roles aren't applyable
    assert len(jobs) == 2

    assert jobs[0].external_id == "81a6c511-64f1-435e-9a5c-3ec2cf868e30"
    assert jobs[0].source == "ashby"
    assert jobs[0].title == "Backend Engineer"
    assert jobs[0].company == "totally-fake-co"
    assert jobs[0].location == "Bangalore HQ"
    assert str(jobs[0].url) == "https://jobs.ashbyhq.com/acme/81a6c511"
    assert jobs[0].description == "Requires 3+ years of experience."

    assert jobs[1].location is None
    assert jobs[1].description is None


@respx.mock
async def test_an_empty_board_is_not_an_error() -> None:
    respx.get(BOARD_URL).mock(return_value=httpx.Response(200, json={"jobs": []}))

    assert await fetch_ashby_jobs("totally-fake-co") == []


@respx.mock
async def test_an_unknown_board_raises() -> None:
    """Ashby 404s an unknown slug, which must surface rather than look like an
    empty board — an empty board would be read as "every job closed".
    """
    respx.get(BOARD_URL).mock(return_value=httpx.Response(404))

    try:
        await fetch_ashby_jobs("totally-fake-co")
    except httpx.HTTPStatusError:
        return
    raise AssertionError("expected an HTTPStatusError for a 404 board")
