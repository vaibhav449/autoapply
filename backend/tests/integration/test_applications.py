import base64
from unittest.mock import AsyncMock, patch

from app.models.application import Application, ApplicationState
from app.models.job import Job as JobModel
from app.models.profile import Profile
from app.services.applications import apply_transition, get_or_create_application
from app.services.discovery.liveness import Liveness


async def _make_profile_and_job(db) -> tuple[Profile, JobModel]:
    profile = Profile(
        name="Test Candidate", email="test@example.dev", resume_text="...", years_experience=1.0
    )
    job = JobModel(
        external_id="app-test-1",
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
    return profile, job


async def test_get_or_create_is_idempotent(db) -> None:
    profile, job = await _make_profile_and_job(db)

    first = await get_or_create_application(profile, job, db)
    second = await get_or_create_application(profile, job, db)

    assert first.id == second.id
    assert first.state == ApplicationState.INTERESTED


async def test_apply_transition_sets_submitted_at_only_on_submitted(db) -> None:
    profile, job = await _make_profile_and_job(db)
    application = await get_or_create_application(profile, job, db)

    await apply_transition(application, ApplicationState.TAILORING, db)
    assert application.submitted_at is None

    await apply_transition(application, ApplicationState.READY_FOR_REVIEW, db)
    await apply_transition(application, ApplicationState.APPROVED, db)
    await apply_transition(application, ApplicationState.SUBMITTED, db)

    assert application.state == ApplicationState.SUBMITTED
    assert application.submitted_at is not None


async def test_create_application_endpoint_is_idempotent(db, client) -> None:
    profile, job = await _make_profile_and_job(db)

    first = await client.post(
        "/api/v1/applications/", json={"profile_id": profile.id, "job_id": job.id}
    )
    second = await client.post(
        "/api/v1/applications/", json={"profile_id": profile.id, "job_id": job.id}
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["state"] == "interested"


async def test_illegal_transition_via_endpoint_is_409(db, client) -> None:
    profile, job = await _make_profile_and_job(db)
    application = Application(profile_id=profile.id, job_id=job.id)
    db.add(application)
    await db.commit()
    await db.refresh(application)

    response = await client.post(
        f"/api/v1/applications/{application.id}/transition",
        json={"target_state": "submitted"},
    )

    assert response.status_code == 409


async def test_create_application_404s_for_unknown_job(db, client) -> None:
    profile = Profile(
        name="Test Candidate", email="test@example.dev", resume_text="...", years_experience=1.0
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)

    response = await client.post(
        "/api/v1/applications/", json={"profile_id": profile.id, "job_id": 999999}
    )

    assert response.status_code == 404


async def test_tailoring_is_blocked_when_the_posting_has_closed(db, client) -> None:
    """The guard sits at interested -> tailoring because that is the first step
    that costs real money: two LLM generations plus a grounding verification pass.
    """
    profile, job = await _make_profile_and_job(db)
    application = await get_or_create_application(profile, job, db)

    with patch(
        "app.api.v1.routers.applications.check_job_liveness",
        new=AsyncMock(return_value=Liveness.CLOSED),
    ):
        response = await client.post(
            f"/api/v1/applications/{application.id}/transition",
            json={"target_state": "tailoring"},
        )

    assert response.status_code == 409
    assert "no longer accepting applications" in response.json()["detail"]

    await db.refresh(application)
    await db.refresh(job)
    assert application.state == ApplicationState.INTERESTED
    # a confirmed closure is recorded, so the job leaves ranking too
    assert job.closed_at is not None


async def test_tailoring_proceeds_when_liveness_cannot_be_checked(db, client) -> None:
    """Aggregator listings can never be verified, so UNVERIFIABLE must not block
    the user — it would make every Adzuna job unusable.
    """
    profile, job = await _make_profile_and_job(db)
    application = await get_or_create_application(profile, job, db)

    with patch(
        "app.api.v1.routers.applications.check_job_liveness",
        new=AsyncMock(return_value=Liveness.UNVERIFIABLE),
    ):
        response = await client.post(
            f"/api/v1/applications/{application.id}/transition",
            json={"target_state": "tailoring"},
        )

    assert response.status_code == 200
    await db.refresh(application)
    assert application.state == ApplicationState.TAILORING
    await db.refresh(job)
    assert job.closed_at is None


async def test_liveness_is_not_checked_on_unrelated_transitions(db, client) -> None:
    profile, job = await _make_profile_and_job(db)
    application = await get_or_create_application(profile, job, db)

    checker = AsyncMock(return_value=Liveness.OPEN)
    with patch("app.api.v1.routers.applications.check_job_liveness", new=checker):
        response = await client.post(
            f"/api/v1/applications/{application.id}/transition",
            json={"target_state": "rejected_by_user"},
        )

    assert response.status_code == 200
    checker.assert_not_awaited()


async def test_get_application_returns_it(db, client) -> None:
    profile, job = await _make_profile_and_job(db)
    application = await get_or_create_application(profile, job, db)

    response = await client.get(f"/api/v1/applications/{application.id}")

    assert response.status_code == 200
    assert response.json()["id"] == application.id
    assert response.json()["profile_id"] == profile.id
    assert response.json()["job_id"] == job.id


async def test_get_application_404s_for_unknown_id(client) -> None:
    response = await client.get("/api/v1/applications/999999")

    assert response.status_code == 404


async def test_get_application_exposes_legal_next_states(db, client) -> None:
    """The frontend reads this instead of hand-copying ALLOWED_TRANSITIONS."""
    profile, job = await _make_profile_and_job(db)
    application = await get_or_create_application(profile, job, db)

    response = await client.get(f"/api/v1/applications/{application.id}")

    assert set(response.json()["legal_next_states"]) == {"tailoring", "rejected_by_user"}


async def test_fill_form_endpoint_returns_the_result_with_a_base64_screenshot(db, client) -> None:
    profile, job = await _make_profile_and_job(db)
    application = await get_or_create_application(profile, job, db)

    fake_result = {
        "status": "filled",
        "filled_fields": {"#first_name": "Test"},
        "skipped_fields": ["#candidate-location"],
        "screenshot": b"\x89PNG\r\n\x1a\nfake",
    }
    with patch(
        "app.api.v1.routers.applications.fill_application_form",
        new=AsyncMock(return_value=fake_result),
    ):
        response = await client.post(f"/api/v1/applications/{application.id}/fill-form")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "filled"
    assert body["filled_fields"] == {"#first_name": "Test"}
    assert body["skipped_fields"] == ["#candidate-location"]
    assert base64.b64decode(body["screenshot_base64"]) == fake_result["screenshot"]


async def test_fill_form_endpoint_is_422_when_no_adapter_matches_the_job_url(db, client) -> None:
    """_make_profile_and_job's url (example.test) matches no real ATS adapter —
    the honest response is a 4xx telling the caller why, not a crash.
    """
    profile, job = await _make_profile_and_job(db)
    application = await get_or_create_application(profile, job, db)

    response = await client.post(f"/api/v1/applications/{application.id}/fill-form")

    assert response.status_code == 422
    assert "No ATS adapter registered" in response.json()["detail"]


async def test_fill_form_endpoint_404s_for_unknown_application(client) -> None:
    response = await client.post("/api/v1/applications/999999/fill-form")

    assert response.status_code == 404
