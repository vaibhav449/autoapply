import httpx
import respx

from app.services.discovery.smartrecruiters import (
    _description,
    _location,
    fetch_posting_description,
    fetch_smartrecruiters_postings,
    posting_url,
)

LIST_URL = "https://api.smartrecruiters.com/v1/companies/totally-fake-co/postings"


def page(items: list[dict], total: int) -> dict:
    return {"offset": 0, "limit": 100, "totalFound": total, "content": items}


@respx.mock
async def test_listing_follows_pagination_to_the_end() -> None:
    """The board is only valid evidence for closure detection if the whole thing
    is read — a partial sweep would look like the missing jobs had closed.
    """
    first = [{"id": i, "name": f"Job {i}"} for i in range(100)]
    second = [{"id": 100 + i, "name": f"Job {100 + i}"} for i in range(40)]
    route = respx.get(LIST_URL).mock(
        side_effect=[
            httpx.Response(200, json=page(first, 140)),
            httpx.Response(200, json=page(second, 140)),
        ]
    )

    postings = await fetch_smartrecruiters_postings("totally-fake-co")

    assert len(postings) == 140
    assert route.call_count == 2
    assert dict(route.calls[1].request.url.params)["offset"] == "100"


@respx.mock
async def test_listing_stops_on_an_empty_page() -> None:
    """Guards the pagination loop against spinning forever if totalFound overstates
    what the API will actually hand back.
    """
    respx.get(LIST_URL).mock(
        side_effect=[
            httpx.Response(200, json=page([{"id": 1, "name": "Job"}], 999)),
            httpx.Response(200, json=page([], 999)),
        ]
    )

    assert len(await fetch_smartrecruiters_postings("totally-fake-co")) == 1


def test_location_is_flattened_from_its_parts() -> None:
    assert _location({"city": "Pune", "region": "MH", "country": "in"}) == "Pune, MH, IN"
    assert _location({"city": "Mysuru", "country": "in"}) == "Mysuru, IN"
    assert _location({}) is None
    assert _location(None) is None


def test_description_joins_the_ad_sections_in_reading_order() -> None:
    job_ad = {
        "sections": {
            "jobDescription": {"text": "<p>Build things.</p>"},
            "companyDescription": {"text": "<p>We are Acme.</p>"},
            "qualifications": {"text": "<p>6+ Years required.</p>"},
        }
    }

    text = _description(job_ad)

    assert text == "We are Acme.\n\nBuild things.\n\n6+ Years required."


def test_description_of_an_empty_ad_is_none() -> None:
    assert _description({"sections": {}}) is None
    assert _description(None) is None


def test_posting_url_is_the_public_page() -> None:
    assert (
        posting_url("acme", "744000149817139")
        == "https://jobs.smartrecruiters.com/acme/744000149817139"
    )


@respx.mock
async def test_a_failed_detail_fetch_yields_no_description_rather_than_raising() -> None:
    """One unavailable posting must not abort a whole board sweep."""
    respx.get(f"{LIST_URL}/999").mock(return_value=httpx.Response(500))

    async with httpx.AsyncClient() as client:
        assert await fetch_posting_description(client, "totally-fake-co", "999") is None
