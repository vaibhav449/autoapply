from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.draft_answer import DraftAnswer
from app.models.job import Job as JobModel
from app.models.profile import Profile
from app.services.applications import get_or_create_application
from app.services.tailoring.draft_answer import ensure_draft_answer

QUESTION = "Exp working with AWS?"

# Stands in for "whatever the next prompt version is". A literal like "2"
# silently stops testing anything the day GENERATION_VERSION reaches it — which
# is exactly what happened.
BUMPED_VERSION = "version-under-test"


async def _setup(db):
    profile = Profile(
        name="Test Candidate",
        email="test@example.dev",
        resume_text="Backend engineer. No cloud experience.",
        years_experience=1.0,
    )
    job = JobModel(
        external_id="cache-test-1",
        source="greenhouse",
        title="Backend Engineer",
        company="acme",
        location=None,
        url="https://example.test/1",
        description="Build services.",
    )
    db.add_all([profile, job])
    await db.commit()
    profile = (
        await db.execute(
            select(Profile).options(selectinload(Profile.projects)).where(Profile.id == profile.id)
        )
    ).scalar_one()
    await db.refresh(job)
    return profile, job, await get_or_create_application(profile, job, db)


def _generator(text: str):
    return patch(
        "app.services.tailoring.draft_answer.generate_draft_answer",
        new=AsyncMock(return_value=text),
    )


def _clean_grounding():
    return patch(
        "app.services.tailoring.draft_answer.verify_grounding",
        new=AsyncMock(return_value=type("R", (), {"unverified_claims": []})()),
    )


async def test_an_unchanged_answer_is_not_regenerated(db) -> None:
    profile, job, application = await _setup(db)

    with _generator("first") as gen, _clean_grounding():
        await ensure_draft_answer(application, profile, job, QUESTION, db)
        await ensure_draft_answer(application, profile, job, QUESTION, db)

    gen.assert_awaited_once()


async def test_editing_the_resume_regenerates_the_answer(db) -> None:
    """The answer is grounded in the resume, so once that changes the stored
    text is describing a person who no longer exists on paper.
    """
    profile, job, application = await _setup(db)

    with _generator("grounded in the old resume"), _clean_grounding():
        await ensure_draft_answer(application, profile, job, QUESTION, db)

    profile.resume_text = "Backend engineer. Two years on AWS."
    await db.commit()

    with _generator("grounded in the new resume") as gen, _clean_grounding():
        answer = await ensure_draft_answer(application, profile, job, QUESTION, db)

    gen.assert_awaited_once()
    assert answer.answer_text == "grounded in the new resume"


async def test_a_prompt_change_regenerates_the_answer(db) -> None:
    """The bug this exists for: a hallucination was fixed in the prompt and the
    answer written before the fix kept being served, because a plain cache hit
    never looks at whether what produced it still exists.
    """
    profile, job, application = await _setup(db)

    with _generator("I have extensive AWS experience") as gen, _clean_grounding():
        await ensure_draft_answer(application, profile, job, QUESTION, db)
    gen.assert_awaited_once()

    with (
        patch("app.services.tailoring.draft_answer.GENERATION_VERSION", BUMPED_VERSION),
        _generator("My resume does not mention AWS") as gen,
        _clean_grounding(),
    ):
        answer = await ensure_draft_answer(application, profile, job, QUESTION, db)

    gen.assert_awaited_once()
    assert answer.answer_text == "My resume does not mention AWS"


async def test_regenerating_updates_the_row_rather_than_adding_one(db) -> None:
    """(application, question) is unique, and anything already pointing at the
    row should follow the answer rather than the id.
    """
    profile, job, application = await _setup(db)

    with _generator("first") as gen, _clean_grounding():
        original = await ensure_draft_answer(application, profile, job, QUESTION, db)
    original_id = original.id

    with patch("app.services.tailoring.draft_answer.GENERATION_VERSION", BUMPED_VERSION), _generator(
        "second"
    ), _clean_grounding():
        updated = await ensure_draft_answer(application, profile, job, QUESTION, db)

    assert updated.id == original_id
    rows = (
        (await db.execute(select(DraftAnswer).where(DraftAnswer.application_id == application.id)))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert gen is not None


async def test_an_answer_a_person_edited_is_never_regenerated(db, client) -> None:
    """The one thing invalidation must not touch. A candidate's own wording is
    theirs however far the prompt moves on.
    """
    profile, job, application = await _setup(db)

    with _generator("generated text"), _clean_grounding():
        answer = await ensure_draft_answer(application, profile, job, QUESTION, db)

    with patch(
        "app.api.v1.routers.applications.verify_grounding",
        new=AsyncMock(return_value=type("R", (), {"unverified_claims": []})()),
    ):
        edited = await client.patch(
            f"/api/v1/applications/{application.id}/draft-answers/{answer.id}",
            json={"answer_text": "What I actually want to say."},
        )
    assert edited.status_code == 200

    # everything that would normally force a regeneration, at once
    profile.resume_text = "A completely different resume."
    await db.commit()

    with patch("app.services.tailoring.draft_answer.GENERATION_VERSION", BUMPED_VERSION), _generator(
        "regenerated over the human's words"
    ) as gen, _clean_grounding():
        kept = await ensure_draft_answer(application, profile, job, QUESTION, db)

    gen.assert_not_awaited()
    assert kept.answer_text == "What I actually want to say."


def _generator_by_limit(fitting: str, unbounded: str):
    """Stands in for the real generator's behaviour: an answer written with no
    limit in view can run long, and one written against a limit fits it.
    """

    async def generate(profile, job, question_text, max_length=None):
        return unbounded if max_length is None else fitting

    return patch(
        "app.services.tailoring.draft_answer.generate_draft_answer",
        new=AsyncMock(side_effect=generate),
    )


async def test_an_answer_that_already_fits_the_field_is_not_regenerated(db) -> None:
    profile, job, application = await _setup(db)

    with _generator("fits easily") as gen, _clean_grounding():
        await ensure_draft_answer(application, profile, job, QUESTION, db)
        await ensure_draft_answer(application, profile, job, QUESTION, db, max_length=255)

    gen.assert_awaited_once()


async def test_an_answer_too_long_for_the_field_is_regenerated_to_fit(db) -> None:
    """The Capco case: a 301-character answer cached for a question whose field
    holds 255. Reusing it would mean a skipped field on every fill, forever.
    """
    profile, job, application = await _setup(db)

    with _generator("x" * 301), _clean_grounding():
        first = await ensure_draft_answer(application, profile, job, QUESTION, db)

    with _generator("fits now") as gen, _clean_grounding():
        fitted = await ensure_draft_answer(
            application, profile, job, QUESTION, db, max_length=255
        )

    gen.assert_awaited_once()
    assert gen.await_args.args[3] == 255  # the limit reached the generator
    assert fitted.id == first.id  # updated in place, not a second row
    assert fitted.answer_text == "fits now"


async def test_a_fitted_answer_survives_the_generate_button(db) -> None:
    """The limit is left out of the fingerprint on purpose. Were it in, the
    button (no field, no limit) and a fill (limit 255) would each see the
    other's answer as stale and regenerate over it on every visit — paying for
    a new answer each time and never settling on one.
    """
    profile, job, application = await _setup(db)

    with _generator_by_limit(fitting="fits", unbounded="x" * 301) as gen, _clean_grounding():
        await ensure_draft_answer(application, profile, job, QUESTION, db)
        await ensure_draft_answer(application, profile, job, QUESTION, db, max_length=255)
        button = await ensure_draft_answer(application, profile, job, QUESTION, db)
        refill = await ensure_draft_answer(application, profile, job, QUESTION, db, max_length=255)

    assert gen.await_count == 2  # once unbounded, once to fit — then settled
    assert button.answer_text == refill.answer_text == "fits"


async def test_a_person_written_answer_is_never_rewritten_to_fit(db, client) -> None:
    """Too long for the field or not, a candidate's own words stay theirs. The
    fill refuses to write it and leaves that field to them; nothing here
    regenerates over it.
    """
    profile, job, application = await _setup(db)

    with _generator("generated text"), _clean_grounding():
        answer = await ensure_draft_answer(application, profile, job, QUESTION, db)

    their_words = "What I actually want to say, at whatever length I want to say it."
    with patch(
        "app.api.v1.routers.applications.verify_grounding",
        new=AsyncMock(return_value=type("R", (), {"unverified_claims": []})()),
    ):
        edited = await client.patch(
            f"/api/v1/applications/{application.id}/draft-answers/{answer.id}",
            json={"answer_text": their_words},
        )
    assert edited.status_code == 200

    with _generator("rewritten to fit") as gen, _clean_grounding():
        kept = await ensure_draft_answer(application, profile, job, QUESTION, db, max_length=20)

    gen.assert_not_awaited()
    assert kept.answer_text == their_words


async def test_a_question_only_the_candidate_can_answer_stores_nothing(db) -> None:
    """A stored row would show on the application page as the answer."""
    profile, job, application = await _setup(db)

    with _generator("NOT_PROVIDED"), _clean_grounding() as verify:
        result = await ensure_draft_answer(application, profile, job, QUESTION, db)

    assert result is None
    verify.assert_not_awaited()  # nothing to check, nothing paid for
    rows = (
        await db.execute(select(DraftAnswer).where(DraftAnswer.application_id == application.id))
    ).scalars().all()
    assert rows == []


async def test_a_stale_machine_answer_is_removed_once_the_question_is_handed_back(db) -> None:
    """Seen live: rows written under an older prompt kept showing on the page
    as the answer long after current rules stopped producing anything."""
    profile, job, application = await _setup(db)
    with _generator("My current CTC is not specified in the information provided."), (
        _clean_grounding()
    ):
        stale = await ensure_draft_answer(application, profile, job, QUESTION, db)

    with patch(
        "app.services.tailoring.draft_answer.GENERATION_VERSION", BUMPED_VERSION
    ), _generator("NOT_PROVIDED"), _clean_grounding():
        result = await ensure_draft_answer(application, profile, job, QUESTION, db)

    assert result is None
    assert await db.get(DraftAnswer, stale.id) is None


async def test_the_candidates_own_answer_is_kept_even_for_a_handed_back_question(
    db, client
) -> None:
    profile, job, application = await _setup(db)
    with _generator("generated text"), _clean_grounding():
        answer = await ensure_draft_answer(application, profile, job, QUESTION, db)
    with patch(
        "app.api.v1.routers.applications.verify_grounding",
        new=AsyncMock(return_value=type("R", (), {"unverified_claims": []})()),
    ):
        await client.patch(
            f"/api/v1/applications/{application.id}/draft-answers/{answer.id}",
            json={"answer_text": "18 LPA, negotiable."},
        )

    with patch(
        "app.services.tailoring.draft_answer.GENERATION_VERSION", BUMPED_VERSION
    ), _generator("NOT_PROVIDED") as gen, _clean_grounding():
        kept = await ensure_draft_answer(application, profile, job, QUESTION, db)

    gen.assert_not_awaited()
    assert kept.answer_text == "18 LPA, negotiable."


async def test_a_declined_dropdown_removes_its_stale_machine_pick(db) -> None:
    """The same gap on the dropdown path. Seen live on a real application:
    "Do you have any offer in hand? No" still listed as the answer after
    current rules had started leaving the question for the candidate."""
    from app.services.tailoring.draft_answer import ensure_draft_option

    profile, job, application = await _setup(db)
    question, options = "Do you have any offer in hand ?", ["Yes", "No"]
    with patch(
        "app.services.tailoring.draft_answer.choose_draft_option", new=AsyncMock(return_value="No")
    ):
        await ensure_draft_option(application, profile, job, question, options, db)

    with patch(
        "app.services.tailoring.draft_answer.GENERATION_VERSION", BUMPED_VERSION
    ), patch(
        "app.services.tailoring.draft_answer.choose_draft_option", new=AsyncMock(return_value=None)
    ):
        choice = await ensure_draft_option(application, profile, job, question, options, db)

    assert choice is None
    rows = (
        await db.execute(select(DraftAnswer).where(DraftAnswer.application_id == application.id))
    ).scalars().all()
    assert rows == []
