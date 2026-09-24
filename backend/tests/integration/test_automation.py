from typing import get_args
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.automation.base import FillResult, FillStatus
from app.models.application import ApplicationState
from app.models.draft_answer import DraftAnswer
from app.models.fill_attempt import FillAttempt, FillAttemptStatus
from app.models.job import Job as JobModel
from app.models.profile import Profile
from app.services.applications import apply_transition, get_or_create_application
from app.services.automation import (
    NoAdapterForUrl,
    fill_application_form,
    list_fill_attempts,
)


async def _make_profile_and_job(db, url: str = "https://job-boards.greenhouse.io/acme/jobs/1") -> tuple:
    profile = Profile(
        name="Ada Lovelace",
        email="ada@example.dev",
        phone="555-0100",
        location="Bengaluru",
        resume_text="...",
        years_experience=1.0,
    )
    job = JobModel(
        external_id="automation-test-1",
        source="greenhouse",
        title="Backend Engineer",
        company="acme",
        location=None,
        url=url,
        description="Build things.",
    )
    db.add_all([profile, job])
    await db.commit()
    # eager-loaded: profile.full_resume_text (read inside ensure_draft_answer's
    # grounding check) touches profile.projects, and a lazy-load outside the
    # greenlet context db.refresh() runs in raises MissingGreenlet rather than
    # quietly working — same gotcha the real route hit and fixed earlier.
    profile = (
        await db.execute(
            select(Profile).options(selectinload(Profile.projects)).where(Profile.id == profile.id)
        )
    ).scalar_one()
    await db.refresh(job)
    return profile, job


def fake_result(status: str, filled: dict | None = None) -> FillResult:
    return FillResult(status=status, filled_fields=filled or {}, skipped_fields=[], screenshot=b"png")


async def _to_ready_for_review(application, db) -> None:
    await apply_transition(application, ApplicationState.TAILORING, db)
    await apply_transition(application, ApplicationState.READY_FOR_REVIEW, db)


async def test_captcha_required_moves_a_reviewable_application_to_pending_captcha(db) -> None:
    profile, job = await _make_profile_and_job(db)
    application = await get_or_create_application(profile, job, db)
    await _to_ready_for_review(application, db)

    with patch(
        "app.services.automation.GreenhouseFormAdapter.fill",
        new=AsyncMock(return_value=fake_result("captcha_required")),
    ):
        result = await fill_application_form(application, profile, job, db)

    assert result.status == FillAttemptStatus.CAPTCHA_REQUIRED
    assert application.state == ApplicationState.PENDING_CAPTCHA


async def test_captcha_required_from_a_non_reviewable_state_does_not_crash(db) -> None:
    """fill_application_form must stay callable even when the application isn't
    somewhere pending_captcha can legally be reached from — it just leaves the
    state alone rather than raising IllegalStateTransition outward.
    """
    profile, job = await _make_profile_and_job(db)
    application = await get_or_create_application(profile, job, db)
    assert application.state == ApplicationState.INTERESTED

    with patch(
        "app.services.automation.GreenhouseFormAdapter.fill",
        new=AsyncMock(return_value=fake_result("captcha_required")),
    ):
        result = await fill_application_form(application, profile, job, db)

    assert result.status == FillAttemptStatus.CAPTCHA_REQUIRED
    assert application.state == ApplicationState.INTERESTED


async def test_a_clean_fill_leaves_the_state_untouched(db) -> None:
    profile, job = await _make_profile_and_job(db)
    application = await get_or_create_application(profile, job, db)
    await _to_ready_for_review(application, db)

    with patch(
        "app.services.automation.GreenhouseFormAdapter.fill",
        new=AsyncMock(return_value=fake_result("filled", {"#email": "ada@example.dev"})),
    ):
        result = await fill_application_form(application, profile, job, db)

    assert result.status == FillAttemptStatus.FILLED
    assert application.state == ApplicationState.READY_FOR_REVIEW


async def test_fill_uses_an_untailored_base_resume_when_no_variant_is_linked(db) -> None:
    """Application.resume_variant_id is never set by any current workflow — so
    without this fallback, resume_bytes would be None (and #resume skipped) on
    every single fill, not just for applications that happen to lack a variant.
    """
    profile, job = await _make_profile_and_job(db)
    application = await get_or_create_application(profile, job, db)
    await _to_ready_for_review(application, db)
    assert application.resume_variant_id is None

    captured_payload = {}

    async def capture_and_fill(self, application_url, payload):
        captured_payload.update(payload)
        return fake_result("filled")

    with patch("app.services.automation.GreenhouseFormAdapter.fill", new=capture_and_fill):
        await fill_application_form(application, profile, job, db)

    assert captured_payload["resume_bytes"] is not None
    assert captured_payload["resume_bytes"].startswith(b"%PDF-")
    assert captured_payload["resume_filename"] == "Ada_Lovelace_resume.pdf"


async def test_fill_skips_the_resume_rather_than_crashing_on_unrenderable_text(db) -> None:
    """profile.resume_text is arbitrary user-typed text, not LLM output tuned to
    resume_pdf's fold map — a stray character genuinely outside the built-in
    PDF fonts (a name in a non-Latin script, say — resume_pdf's own tests treat
    this the same way) must not take down the entire fill over one field, the
    same honest-skip treatment a combobox gets.
    """
    profile, job = await _make_profile_and_job(db)
    profile.resume_text = "Led growth for वैभव चौबे initiatives."
    application = await get_or_create_application(profile, job, db)
    await _to_ready_for_review(application, db)

    captured_payload = {}

    async def capture_and_fill(self, application_url, payload):
        captured_payload.update(payload)
        return fake_result("filled")

    with patch("app.services.automation.GreenhouseFormAdapter.fill", new=capture_and_fill):
        result = await fill_application_form(application, profile, job, db)

    assert result.status == FillAttemptStatus.FILLED
    assert captured_payload["resume_bytes"] is None


async def test_dropdown_choices_go_through_the_same_cached_path(db) -> None:
    """A dropdown pick is cached per (application, question) exactly like a
    free-text answer, so a retried fill re-selects the same option instead of
    paying for a fresh choice that could land somewhere different.
    """
    profile, job = await _make_profile_and_job(db)
    application = await get_or_create_application(profile, job, db)
    await _to_ready_for_review(application, db)

    captured = {}

    async def capture_and_fill(self, application_url, payload):
        captured["choose_option"] = payload["choose_option"]
        return fake_result("filled")

    with (
        patch("app.services.automation.GreenhouseFormAdapter.fill", new=capture_and_fill),
        patch(
            "app.services.tailoring.draft_answer.choose_draft_option",
            new=AsyncMock(return_value="0-6 Years"),
        ) as mock_choose,
    ):
        await fill_application_form(application, profile, job, db)
        choose_option = captured["choose_option"]

        options = ["0-6 Years", "6-8 Years"]
        first = await choose_option("Total years of experience", options)
        second = await choose_option("Total years of experience", options)

    assert first == second == "0-6 Years"
    mock_choose.assert_awaited_once()  # the second call was a cache hit


async def test_a_declined_dropdown_is_not_cached_as_an_empty_answer(db) -> None:
    profile, job = await _make_profile_and_job(db)
    application = await get_or_create_application(profile, job, db)

    captured = {}

    async def capture_and_fill(self, application_url, payload):
        captured["choose_option"] = payload["choose_option"]
        return fake_result("filled")

    with (
        patch("app.services.automation.GreenhouseFormAdapter.fill", new=capture_and_fill),
        patch(
            "app.services.tailoring.draft_answer.choose_draft_option",
            new=AsyncMock(return_value=None),
        ),
    ):
        await fill_application_form(application, profile, job, db)
        choice = await captured["choose_option"]("Do you have any offer in hand ?", ["Yes", "No"])

    assert choice is None
    rows = (
        await db.execute(
            select(DraftAnswer).where(DraftAnswer.application_id == application.id)
        )
    ).scalars().all()
    assert rows == []


async def test_no_adapter_for_an_unrecognized_url_raises(db) -> None:
    profile, job = await _make_profile_and_job(db, url="https://careers.example.dev/apply/1")
    application = await get_or_create_application(profile, job, db)

    with pytest.raises(NoAdapterForUrl):
        await fill_application_form(application, profile, job, db)


async def test_fill_attempt_status_matches_fill_status(db) -> None:
    """The adapter layer names a status as a Literal and the database as an
    enum, on purpose — a module that drives a browser has no business importing
    a model to get a string. This is what keeps the two lists identical instead
    of trusting that nobody adds a status to one of them alone.
    """
    assert {member.value for member in FillAttemptStatus} == set(get_args(FillStatus))


async def test_the_run_is_recorded_in_full(db) -> None:
    profile, job = await _make_profile_and_job(db)
    application = await get_or_create_application(profile, job, db)
    await _to_ready_for_review(application, db)

    with patch(
        "app.services.automation.GreenhouseFormAdapter.fill",
        new=AsyncMock(return_value=fake_result("filled", {"#email": "ada@example.dev"})),
    ):
        attempt = await fill_application_form(application, profile, job, db)

    stored = (
        await db.execute(select(FillAttempt).where(FillAttempt.id == attempt.id))
    ).scalar_one()
    assert stored.application_id == application.id
    assert stored.filled_fields == {"#email": "ada@example.dev"}
    assert stored.screenshot == b"png"
    assert stored.duration_ms >= 0


async def test_the_attempt_is_kept_even_when_the_state_change_is_illegal(db) -> None:
    """A captcha from a state pending_captcha can't be reached from must not
    take the record of the run down with it — the attempt is committed before
    the transition is tried for exactly this case.
    """
    profile, job = await _make_profile_and_job(db)
    application = await get_or_create_application(profile, job, db)
    assert application.state == ApplicationState.INTERESTED

    with patch(
        "app.services.automation.GreenhouseFormAdapter.fill",
        new=AsyncMock(return_value=fake_result("captcha_required")),
    ):
        await fill_application_form(application, profile, job, db)

    rows = (
        await db.execute(
            select(FillAttempt).where(FillAttempt.application_id == application.id)
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].status == FillAttemptStatus.CAPTCHA_REQUIRED


async def test_reading_attempts_back_never_loads_the_screenshot(db) -> None:
    """has_screenshot is computed in SQL so that listing a run's history does
    not pull every full-page PNG out of Postgres to answer a yes/no question.
    """
    profile, job = await _make_profile_and_job(db)
    application = await get_or_create_application(profile, job, db)

    with patch(
        "app.services.automation.GreenhouseFormAdapter.fill",
        new=AsyncMock(return_value=fake_result("filled")),
    ):
        await fill_application_form(application, profile, job, db)

    rows = await list_fill_attempts(application.id, db)

    assert [row.has_screenshot for row in rows] == [True]
    assert not hasattr(rows[0], "screenshot")


async def test_custom_questions_are_answered_through_the_cached_draft_answer_path(db) -> None:
    """A retried fill (e.g. after a human solves a captcha by hand and the form
    is re-opened) must reuse the same generated answer, not spend a fresh LLM
    call and risk a different one landing in the form the second time.
    """
    profile, job = await _make_profile_and_job(db)
    application = await get_or_create_application(profile, job, db)
    await _to_ready_for_review(application, db)

    captured_callback = {}

    async def capture_and_fill(self, application_url, payload):
        captured_callback["answer_question"] = payload["answer_question"]
        return fake_result("filled")

    with (
        patch("app.services.automation.GreenhouseFormAdapter.fill", new=capture_and_fill),
        patch(
            "app.services.tailoring.draft_answer.generate_draft_answer",
            new=AsyncMock(return_value="A real, grounded answer."),
        ) as mock_generate,
        patch(
            "app.services.tailoring.draft_answer.verify_grounding",
            new=AsyncMock(return_value=type("R", (), {"unverified_claims": []})()),
        ),
    ):
        await fill_application_form(application, profile, job, db)
        answer_question = captured_callback["answer_question"]

        first = await answer_question("Why do you want this role?", None)
        second = await answer_question("Why do you want this role?", None)

    assert first == second == "A real, grounded answer."
    mock_generate.assert_awaited_once()  # second call was a cache hit, not a regeneration


async def test_the_fields_limit_reaches_the_generator(db) -> None:
    """The adapter reads the limit off the live field; this is the path that
    carries it the rest of the way, to where the answer is actually written.
    """
    profile, job = await _make_profile_and_job(db)
    application = await get_or_create_application(profile, job, db)

    captured = {}

    async def capture_and_fill(self, application_url, payload):
        captured["answer_question"] = payload["answer_question"]
        return fake_result("filled")

    with (
        patch("app.services.automation.GreenhouseFormAdapter.fill", new=capture_and_fill),
        patch(
            "app.services.tailoring.draft_answer.generate_draft_answer",
            new=AsyncMock(return_value="Fits."),
        ) as mock_generate,
        patch(
            "app.services.tailoring.draft_answer.verify_grounding",
            new=AsyncMock(return_value=type("R", (), {"unverified_claims": []})()),
        ),
    ):
        await fill_application_form(application, profile, job, db)
        answer = await captured["answer_question"]("How many years with React?", 255)

    assert answer == "Fits."
    assert mock_generate.await_args.args[3] == 255


async def test_a_question_only_the_candidate_can_answer_reaches_the_adapter_as_none(db) -> None:
    profile, job = await _make_profile_and_job(db)
    application = await get_or_create_application(profile, job, db)

    captured = {}

    async def capture_and_fill(self, application_url, payload):
        captured["answer_question"] = payload["answer_question"]
        return fake_result("filled")

    with (
        patch("app.services.automation.GreenhouseFormAdapter.fill", new=capture_and_fill),
        patch(
            "app.services.tailoring.draft_answer.generate_draft_answer",
            new=AsyncMock(return_value="NOT_PROVIDED"),
        ),
    ):
        await fill_application_form(application, profile, job, db)
        answer = await captured["answer_question"]("What is your expected CTC?", None)

    assert answer is None
