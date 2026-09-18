from unittest.mock import AsyncMock, patch

from app.models.job import Job as JobModel


async def test_get_job_returns_it(db, client) -> None:
    job = JobModel(
        external_id="jobs-router-test-1",
        source="greenhouse",
        title="Backend Engineer",
        company="acme",
        location="Remote",
        url="https://example.test/1",
        description="Build things.",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    response = await client.get(f"/api/v1/jobs/{job.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Backend Engineer"
    assert body["company"] == "acme"


async def test_get_job_404s_for_unknown_id(client) -> None:
    response = await client.get("/api/v1/jobs/999999")

    assert response.status_code == 404


async def test_get_job_does_not_shadow_the_discover_routes(client) -> None:
    """/{job_id} matches exactly one path segment, so it must not intercept the
    two-segment /discover/* routes declared after it.
    """
    with patch(
        "app.api.v1.routers.jobs.discover_greenhouse_jobs", new=AsyncMock(return_value=[])
    ) as mock_discover:
        response = await client.get("/api/v1/jobs/discover/greenhouse", params={"company": "acme"})

    assert response.status_code == 200
    mock_discover.assert_awaited_once()
