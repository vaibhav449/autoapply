from unittest.mock import AsyncMock, patch

from app.models.job import Job as JobModel
from app.services.scoring.requirements import JobRequirements, ensure_job_requirements


async def test_second_call_uses_cache_not_a_second_llm_call(db) -> None:
    job = JobModel(
        external_id="cache-test-1",
        source="greenhouse",
        title="Backend Engineer",
        company="acme",
        location=None,
        url="https://example.test/jobs/1",
        description="Requires 2+ years of experience.",
    )
    db.add(job)
    await db.commit()

    fake_requirements = JobRequirements(min_years_experience=2.0)
    with patch(
        "app.services.scoring.requirements.extract_job_requirements",
        new=AsyncMock(return_value=fake_requirements),
    ) as mock_extract:
        first = await ensure_job_requirements(job, db)
        second = await ensure_job_requirements(job, db)

    assert mock_extract.await_count == 1
    assert first == fake_requirements
    assert second == fake_requirements
    assert job.requirements == fake_requirements.model_dump()


async def test_job_with_no_description_skips_llm_entirely(db) -> None:
    job = JobModel(
        external_id="cache-test-2",
        source="greenhouse",
        title="Designer",
        company="acme",
        location=None,
        url="https://example.test/jobs/2",
        description=None,
    )
    db.add(job)
    await db.commit()

    with patch(
        "app.services.scoring.requirements.extract_job_requirements",
        new=AsyncMock(),
    ) as mock_extract:
        requirements = await ensure_job_requirements(job, db)

    mock_extract.assert_not_awaited()
    assert requirements == JobRequirements()
