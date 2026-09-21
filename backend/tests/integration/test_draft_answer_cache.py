from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.draft_answer import DraftAnswer
from app.models.job import Job as JobModel
from app.models.profile import Profile
from app.services.applications import get_or_create_application
from app.services.tailoring.draft_answer import ensure_draft_answer

QUESTION = "Exp working with AWS?"


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
        patch("app.services.tailoring.draft_answer.GENERATION_VERSION", "2"),
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

    with patch("app.services.tailoring.draft_answer.GENERATION_VERSION", "2"), _generator(
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

    with patch("app.services.tailoring.draft_answer.GENERATION_VERSION", "99"), _generator(
        "regenerated over the human's words"
    ) as gen, _clean_grounding():
        kept = await ensure_draft_answer(application, profile, job, QUESTION, db)

    gen.assert_not_awaited()
    assert kept.answer_text == "What I actually want to say."
