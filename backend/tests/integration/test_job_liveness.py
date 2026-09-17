from sqlalchemy import select

from app.models.job import Job as JobModel
from app.schemas.job import Job
from app.services.discovery import reconcile_board_sweep, save_jobs


def posting(external_id: str, source: str = "greenhouse", company: str = "acme") -> Job:
    return Job(
        external_id=external_id,
        source=source,
        title=f"Engineer {external_id}",
        company=company,
        location=None,
        url=f"https://example.test/{external_id}",
        description="Requires 2+ years of experience.",
    )


async def board(db, source: str = "greenhouse", company: str = "acme") -> dict[str, JobModel]:
    result = await db.execute(
        select(JobModel).where(JobModel.source == source, JobModel.company == company)
    )
    return {job.external_id: job for job in result.scalars().all()}


async def sweep(db, ids: list[str], source: str = "greenhouse", company: str = "acme") -> None:
    await save_jobs([posting(i, source, company) for i in ids], db)
    await reconcile_board_sweep(source, company, db)
    db.expire_all()


async def test_a_job_present_in_every_sweep_is_never_closed(db) -> None:
    await sweep(db, ["a", "b"])
    await sweep(db, ["a", "b"])
    await sweep(db, ["a", "b"])

    jobs = await board(db)
    assert jobs["a"].closed_at is None
    assert jobs["a"].missed_sweeps == 0


async def test_one_missed_sweep_is_not_enough_to_close(db) -> None:
    """A single flaky fetch must not bury a live posting."""
    await sweep(db, ["a", "b"])
    await sweep(db, ["a"])

    jobs = await board(db)
    assert jobs["b"].missed_sweeps == 1
    assert jobs["b"].closed_at is None


async def test_two_consecutive_misses_close_the_job(db) -> None:
    await sweep(db, ["a", "b"])
    await sweep(db, ["a"])
    await sweep(db, ["a"])

    jobs = await board(db)
    assert jobs["b"].missed_sweeps >= 2
    assert jobs["b"].closed_at is not None
    assert jobs["a"].closed_at is None


async def test_a_reappearing_job_is_reopened(db) -> None:
    await sweep(db, ["a", "b"])
    await sweep(db, ["a"])
    await sweep(db, ["a"])
    assert (await board(db))["b"].closed_at is not None

    await sweep(db, ["a", "b"])

    jobs = await board(db)
    assert jobs["b"].closed_at is None
    assert jobs["b"].missed_sweeps == 0


async def test_keyword_search_sources_are_never_expired(db) -> None:
    """Absence from an Adzuna result set means "didn't match today's query", not
    "closed" — expiring on it would delete live jobs.
    """
    await sweep(db, ["a", "b"], source="adzuna", company="acme")
    await sweep(db, ["a"], source="adzuna", company="acme")
    await sweep(db, ["a"], source="adzuna", company="acme")

    jobs = await board(db, source="adzuna")
    assert jobs["b"].closed_at is None
    assert jobs["b"].missed_sweeps == 0


async def test_a_failed_poll_stamps_nobody_and_closes_nobody(db) -> None:
    """The reason staleness is judged against the board's own newest sighting
    rather than wall-clock time: a poll that returns nothing must be a no-op.
    """
    await sweep(db, ["a", "b"])

    await save_jobs([], db)
    await reconcile_board_sweep("greenhouse", "acme", db)
    db.expire_all()

    jobs = await board(db)
    assert jobs["a"].missed_sweeps == 0
    assert jobs["b"].missed_sweeps == 0
    assert jobs["b"].closed_at is None


async def test_resighting_updates_last_seen_without_clobbering_content(db) -> None:
    await sweep(db, ["a"])
    original = (await board(db))["a"]
    first_seen = original.last_seen_at
    original_title = original.title

    changed = posting("a")
    changed.title = "Totally Different Title"
    await save_jobs([changed], db)
    db.expire_all()

    job = (await board(db))["a"]
    assert job.last_seen_at >= first_seen
    assert job.title == original_title
