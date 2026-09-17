from unittest.mock import AsyncMock, patch

from app.models.job import Job as JobModel
from app.models.profile import Profile


async def test_second_request_is_cached_not_a_second_llm_call(db, client) -> None:
    profile = Profile(
        name="Test Candidate",
        email="test@example.dev",
        resume_text="...",
        years_experience=1.0,
        embedding=None,
    )
    job = JobModel(
        external_id="cover-letter-test-1",
        source="greenhouse",
        title="Backend Engineer",
        company="acme",
        location=None,
        url="https://example.test/1",
        description="...",
    )
    db.add_all([profile, job])
    await db.commit()
    await db.refresh(profile)
    await db.refresh(job)

    with patch(
        "app.services.tailoring.cover_letter.generate_cover_letter",
        new=AsyncMock(return_value="Generated pitch text."),
    ) as mock_generate:
        first = await client.get(f"/api/v1/profiles/{profile.id}/jobs/{job.id}/cover-letter")
        second = await client.get(f"/api/v1/profiles/{profile.id}/jobs/{job.id}/cover-letter")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["content"] == "Generated pitch text."
    assert first.json()["id"] == second.json()["id"]  # same cached row both times
    assert mock_generate.await_count == 1


async def test_404s_for_unknown_job(db, client) -> None:
    profile = Profile(
        name="Test Candidate", email="test@example.dev", resume_text="...", years_experience=1.0
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)

    response = await client.get(f"/api/v1/profiles/{profile.id}/jobs/999999/cover-letter")

    assert response.status_code == 404


async def test_404s_for_unknown_profile(db, client) -> None:
    job = JobModel(
        external_id="cover-letter-test-2",
        source="greenhouse",
        title="Backend Engineer",
        company="acme",
        location=None,
        url="https://example.test/2",
        description="...",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    response = await client.get(f"/api/v1/profiles/999999/jobs/{job.id}/cover-letter")

    assert response.status_code == 404
