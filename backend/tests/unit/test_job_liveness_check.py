from datetime import UTC, datetime

import httpx
import respx

from app.models.job import Job as JobModel
from app.services.discovery.liveness import Liveness, check_job_liveness

GREENHOUSE_URL = "https://boards-api.greenhouse.io/v1/boards/stripe/jobs/123"
LEVER_URL = "https://api.lever.co/v0/postings/palantir/abc"


def make_job(source: str = "greenhouse", **overrides) -> JobModel:
    fields = {
        "external_id": "123" if source == "greenhouse" else "abc",
        "source": source,
        "title": "Engineer",
        "company": "stripe" if source == "greenhouse" else "palantir",
        "location": None,
        "url": "https://example.test/1",
        "description": None,
    }
    return JobModel(**{**fields, **overrides})


@respx.mock
async def test_a_listed_greenhouse_job_is_open() -> None:
    respx.get(GREENHOUSE_URL).mock(return_value=httpx.Response(200, json={"id": 123}))

    assert await check_job_liveness(make_job()) is Liveness.OPEN


@respx.mock
async def test_a_404_means_closed() -> None:
    respx.get(GREENHOUSE_URL).mock(return_value=httpx.Response(404))

    assert await check_job_liveness(make_job()) is Liveness.CLOSED


@respx.mock
async def test_lever_postings_are_checked_too() -> None:
    respx.get(LEVER_URL).mock(return_value=httpx.Response(404))

    assert await check_job_liveness(make_job(source="lever")) is Liveness.CLOSED


@respx.mock
async def test_aggregator_listings_are_unverifiable_without_any_request() -> None:
    """Adzuna landing pages 403 both plain HTTP and a real browser, so there is no
    honest answer — and no point spending a request to find that out again.
    """
    route = respx.route(host__in=["www.adzuna.in", "api.adzuna.com"])

    verdict = await check_job_liveness(make_job(source="adzuna", company="TalentXO"))

    assert verdict is Liveness.UNVERIFIABLE
    assert not route.called


@respx.mock
async def test_an_already_closed_job_short_circuits() -> None:
    route = respx.get(GREENHOUSE_URL)

    verdict = await check_job_liveness(make_job(closed_at=datetime.now(UTC)))

    assert verdict is Liveness.CLOSED
    assert not route.called


@respx.mock
async def test_a_network_failure_is_not_evidence_of_closure() -> None:
    """Our own timeout must never be reported as an employer closing a role."""
    respx.get(GREENHOUSE_URL).mock(side_effect=httpx.ConnectTimeout("boom"))

    assert await check_job_liveness(make_job()) is Liveness.UNVERIFIABLE


@respx.mock
async def test_a_server_error_is_unverifiable_not_closed() -> None:
    respx.get(GREENHOUSE_URL).mock(return_value=httpx.Response(500))

    assert await check_job_liveness(make_job()) is Liveness.UNVERIFIABLE
