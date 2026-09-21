from datetime import UTC, datetime

from app.models.application import ApplicationState
from app.models.application_outcome import OutcomeKind
from app.models.job import Job as JobModel
from app.models.profile import Profile
from app.services.applications import apply_transition, get_or_create_application, record_outcome


async def _submitted_application(db):
    profile = Profile(
        name="Test Candidate", email="test@example.dev", resume_text="...", years_experience=1.0
    )
    job = JobModel(
        external_id="outcome-test-1",
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

    application = await get_or_create_application(profile, job, db)
    for state in (
        ApplicationState.TAILORING,
        ApplicationState.READY_FOR_REVIEW,
        ApplicationState.APPROVED,
        ApplicationState.SUBMITTED,
    ):
        await apply_transition(application, state, db)
    return application


async def test_recording_an_outcome_moves_a_submitted_application_along(db) -> None:
    application = await _submitted_application(db)

    outcome = await record_outcome(application, OutcomeKind.REJECTED, None, None, db)

    assert outcome.kind is OutcomeKind.REJECTED
    assert application.state is ApplicationState.RESPONSE_TRACKED


async def test_every_outcome_is_kept_not_just_the_latest(db) -> None:
    """The point of a log over a state column: MVP.md's funnel counts an
    application that reached an interview even when it was later rejected, and
    a single current-state field can only remember the last thing to happen.
    """
    application = await _submitted_application(db)

    await record_outcome(application, OutcomeKind.INTERVIEW, "phone screen", None, db)
    await record_outcome(application, OutcomeKind.REJECTED, "after onsite", None, db)

    kinds = [row.kind for row in await _outcomes_for(db, application.id)]
    assert kinds == [OutcomeKind.INTERVIEW, OutcomeKind.REJECTED]


async def test_a_second_outcome_leaves_the_state_alone(db) -> None:
    """Hearing back twice is normal. Only the first move has anywhere to go, and
    the second must not raise on an illegal transition.
    """
    application = await _submitted_application(db)

    await record_outcome(application, OutcomeKind.INTERVIEW, None, None, db)
    await record_outcome(application, OutcomeKind.OFFER, None, None, db)

    assert application.state is ApplicationState.RESPONSE_TRACKED


async def test_an_outcome_can_be_filed_under_the_day_it_happened(db) -> None:
    application = await _submitted_application(db)
    arrived = datetime(2026, 9, 1, 9, 30, tzinfo=UTC)

    outcome = await record_outcome(application, OutcomeKind.REJECTED, None, arrived, db)

    assert outcome.occurred_at == arrived
    # and it is not just the moment it was typed in
    assert outcome.occurred_at != outcome.created_at


async def test_outcome_endpoints_round_trip(db, client) -> None:
    application = await _submitted_application(db)

    created = await client.post(
        f"/api/v1/applications/{application.id}/outcomes",
        json={"kind": "interview", "note": "30 min with the hiring manager"},
    )
    assert created.status_code == 200
    assert created.json()["kind"] == "interview"
    assert created.json()["note"] == "30 min with the hiring manager"

    listed = await client.get(f"/api/v1/applications/{application.id}/outcomes")
    assert listed.status_code == 200
    assert [row["kind"] for row in listed.json()] == ["interview"]

    moved = await client.get(f"/api/v1/applications/{application.id}")
    assert moved.json()["state"] == "response_tracked"


async def test_outcome_endpoint_rejects_a_kind_that_is_not_real(db, client) -> None:
    application = await _submitted_application(db)

    response = await client.post(
        f"/api/v1/applications/{application.id}/outcomes",
        json={"kind": "ghosted_me_horribly"},
    )

    assert response.status_code == 422


async def test_outcomes_404_for_an_unknown_application(client) -> None:
    assert (await client.get("/api/v1/applications/999999/outcomes")).status_code == 404
    assert (
        await client.post("/api/v1/applications/999999/outcomes", json={"kind": "offer"})
    ).status_code == 404


async def _outcomes_for(db, application_id):
    from sqlalchemy import select

    from app.models.application_outcome import ApplicationOutcome

    result = await db.execute(
        select(ApplicationOutcome)
        .where(ApplicationOutcome.application_id == application_id)
        .order_by(ApplicationOutcome.occurred_at)
    )
    return list(result.scalars().all())
