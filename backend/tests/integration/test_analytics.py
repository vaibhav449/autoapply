from app.models.application import ApplicationState
from app.models.application_outcome import OutcomeKind
from app.models.fill_attempt import FillAttempt, FillAttemptStatus
from app.models.job import Job as JobModel
from app.models.profile import Profile
from app.models.resume_variant import ResumeVariant
from app.services.analytics import application_analytics
from app.services.applications import apply_transition, get_or_create_application, record_outcome

TO_SUBMITTED = (
    ApplicationState.TAILORING,
    ApplicationState.READY_FOR_REVIEW,
    ApplicationState.APPROVED,
    ApplicationState.SUBMITTED,
)


async def _profile(db) -> Profile:
    profile = Profile(
        name="Test Candidate", email="test@example.dev", resume_text="...", years_experience=1.0
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


async def _job(db, external_id: str) -> JobModel:
    job = JobModel(
        external_id=external_id,
        source="greenhouse",
        title="Backend Engineer",
        company="acme",
        location=None,
        url=f"https://example.test/{external_id}",
        description="...",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def _submitted(db, profile, external_id, variant=None):
    application = await get_or_create_application(profile, await _job(db, external_id), db)
    if variant is not None:
        application.resume_variant_id = variant.id
        await db.commit()
    for state in TO_SUBMITTED:
        await apply_transition(application, state, db)
    return application


async def test_an_empty_pipeline_reports_zeroes_not_nulls(db) -> None:
    summary = await application_analytics(db)

    assert summary.started == 0
    assert summary.submitted == 0
    assert summary.responded == 0
    assert summary.variants == []


async def test_the_funnel_counts_each_stage_that_was_recorded(db) -> None:
    profile = await _profile(db)
    interviewed = await _submitted(db, profile, "a")
    rejected = await _submitted(db, profile, "b")
    await _submitted(db, profile, "c")  # submitted, nothing heard yet
    await get_or_create_application(profile, await _job(db, "d"), db)  # never sent

    await record_outcome(interviewed, OutcomeKind.INTERVIEW, None, None, db)
    await record_outcome(rejected, OutcomeKind.REJECTED, None, None, db)

    summary = await application_analytics(db)

    assert summary.started == 4
    assert summary.submitted == 3
    assert summary.responded == 2
    assert summary.interviewed == 1


async def test_one_application_with_several_outcomes_is_counted_once(db) -> None:
    """An interview then a rejection is two rows and one application — counting
    rows here would report a response rate above 100%.
    """
    profile = await _profile(db)
    application = await _submitted(db, profile, "a")

    await record_outcome(application, OutcomeKind.INTERVIEW, None, None, db)
    await record_outcome(application, OutcomeKind.REJECTED, None, None, db)

    summary = await application_analytics(db)

    assert summary.responded == 1
    assert summary.interviewed == 1
    assert summary.by_outcome == {"interview": 1, "rejected": 1}


async def test_a_recorded_silence_is_not_a_response(db) -> None:
    """"Heard nothing and I am closing this out" is worth recording, but it is
    the opposite of a reply and must not inflate the response rate.
    """
    profile = await _profile(db)
    application = await _submitted(db, profile, "a")

    await record_outcome(application, OutcomeKind.NO_RESPONSE, None, None, db)

    summary = await application_analytics(db)

    assert summary.submitted == 1
    assert summary.responded == 0
    assert summary.by_outcome == {"no_response": 1}


async def test_variant_performance_ignores_applications_never_sent(db) -> None:
    """An unsent application cannot have drawn a reply, so counting it in the
    denominator would dilute every variant with work nobody ever submitted.
    """
    profile = await _profile(db)
    variant = ResumeVariant(
        profile_id=profile.id, role_label="Backend Engineer", generated_content="x"
    )
    db.add(variant)
    await db.commit()
    await db.refresh(variant)

    answered = await _submitted(db, profile, "a", variant)
    await _submitted(db, profile, "b", variant)
    unsent = await get_or_create_application(profile, await _job(db, "c"), db)
    unsent.resume_variant_id = variant.id
    await db.commit()

    await record_outcome(answered, OutcomeKind.INTERVIEW, None, None, db)

    summary = await application_analytics(db)

    assert len(summary.variants) == 1
    row = summary.variants[0]
    assert row.role_label == "Backend Engineer"
    assert row.submitted == 2
    assert row.responded == 1
    assert row.interviews == 1


async def test_summary_endpoint_returns_the_shape_the_page_reads(db, client) -> None:
    profile = await _profile(db)
    await _submitted(db, profile, "a")

    response = await client.get("/api/v1/analytics/")

    assert response.status_code == 200
    body = response.json()
    assert body["submitted"] == 1
    assert body["by_state"] == {"submitted": 1}
    assert body["by_outcome"] == {}
    assert body["variants"] == []
    assert body["fill_runs"] == 0
    assert body["skipped_fields"] == []


async def _attempt(db, application, skipped: list[str]) -> None:
    db.add(
        FillAttempt(
            application_id=application.id,
            status=FillAttemptStatus.FILLED,
            filled_fields={"#email": "test@example.dev"},
            skipped_fields=skipped,
            screenshot=None,
            duration_ms=1000,
        )
    )
    await db.commit()


async def test_the_most_skipped_fields_are_ranked_by_applications_affected(db) -> None:
    """The ranking answers "what should the adapters learn next", so it counts
    applications rather than runs — a form filled three times over is one
    problem, not three.
    """
    profile = await _profile(db)
    first = await _submitted(db, profile, "a")
    second = await _submitted(db, profile, "b")

    # Twice on the same application: one problem, seen twice.
    await _attempt(db, first, ["#candidate-location", "Notice period"])
    await _attempt(db, first, ["#candidate-location", "Notice period"])
    # Once elsewhere, so this one has reached two applications and outranks it.
    await _attempt(db, second, ["#candidate-location"])

    summary = await application_analytics(db)

    assert summary.fill_runs == 3
    assert [(row.field, row.applications, row.runs) for row in summary.skipped_fields] == [
        ("#candidate-location", 2, 3),
        ("Notice period", 1, 2),
    ]


async def test_a_run_that_skipped_nothing_contributes_no_rows(db) -> None:
    profile = await _profile(db)
    application = await _submitted(db, profile, "a")
    await _attempt(db, application, [])

    summary = await application_analytics(db)

    assert summary.fill_runs == 1
    assert summary.skipped_fields == []
