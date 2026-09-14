from unittest.mock import AsyncMock, patch

from app.models.job import Job as JobModel
from app.services.tailoring.resume_variant import find_representative_jds
from tests.integration.conftest import vector


async def test_finds_closest_jobs_and_excludes_ones_without_embedding_or_description(db) -> None:
    close_job = JobModel(
        external_id="close",
        source="greenhouse",
        title="Backend Engineer",
        company="acme",
        location=None,
        url="https://example.test/1",
        description="Real description.",
        embedding=vector(1.0, 0.0),
    )
    far_job = JobModel(
        external_id="far",
        source="greenhouse",
        title="Designer",
        company="acme",
        location=None,
        url="https://example.test/2",
        description="Real description.",
        embedding=vector(0.0, 1.0),
    )
    no_embedding_job = JobModel(
        external_id="no-embedding",
        source="greenhouse",
        title="Backend Engineer",
        company="acme",
        location=None,
        url="https://example.test/3",
        description="Real description.",
        embedding=None,
    )
    no_description_job = JobModel(
        external_id="no-description",
        source="greenhouse",
        title="Backend Engineer",
        company="acme",
        location=None,
        url="https://example.test/4",
        description=None,
        embedding=vector(1.0, 0.0),
    )
    db.add_all([close_job, far_job, no_embedding_job, no_description_job])
    await db.commit()

    with patch(
        "app.services.tailoring.resume_variant.embed_text",
        new=AsyncMock(return_value=vector(1.0, 0.0)),
    ):
        results = await find_representative_jds("Backend Engineer", db, limit=10)

    titles = [job.external_id for job in results]
    assert titles == ["close", "far"]  # closest first, both no-embedding/no-description excluded
