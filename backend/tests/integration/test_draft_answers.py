from unittest.mock import AsyncMock, patch

from app.models.job import Job as JobModel
from app.models.profile import Profile
from app.services.applications import get_or_create_application
from app.services.tailoring.grounding import VerificationResult


async def _make_profile_and_job(db) -> tuple[Profile, JobModel]:
    profile = Profile(
        name="Test Candidate", email="test@example.dev", resume_text="...", years_experience=1.0
    )
    job = JobModel(
        external_id="draft-answer-test-1",
        source="greenhouse",
        title="Backend Engineer",
        company="acme",
        location=None,
        url="https://example.test/1",
        description="Build our core services.",
    )
    db.add_all([profile, job])
    await db.commit()
    await db.refresh(profile)
    await db.refresh(job)
    return profile, job


def _mocked_generation(answer: str = "I'm drawn to this role because...", claims: list[str] | None = None):
    return (
        patch(
            "app.services.tailoring.draft_answer.generate_draft_answer",
            new=AsyncMock(return_value=answer),
        ),
        patch(
            "app.services.tailoring.draft_answer.verify_grounding",
            new=AsyncMock(return_value=VerificationResult(unverified_claims=claims or [])),
        ),
    )


async def test_create_draft_answer_persists_and_returns_it(db, client) -> None:
    profile, job = await _make_profile_and_job(db)
    application = await get_or_create_application(profile, job, db)

    gen_patch, verify_patch = _mocked_generation(
        "I'm excited about backend work here.", claims=["led a team of 10"]
    )
    with gen_patch, verify_patch:
        response = await client.post(
            f"/api/v1/applications/{application.id}/draft-answers",
            json={"question_text": "Why do you want to work here?"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["question_text"] == "Why do you want to work here?"
    assert body["answer_text"] == "I'm excited about backend work here."
    assert body["unverified_claims"] == ["led a team of 10"]
    assert body["application_id"] == application.id


async def test_second_call_for_the_same_question_is_a_cache_hit(db, client) -> None:
    """Same idempotency discipline as ensure_cover_letter: asking twice returns
    the same row rather than spending a second pair of LLM calls.
    """
    profile, job = await _make_profile_and_job(db)
    application = await get_or_create_application(profile, job, db)

    gen_patch, verify_patch = _mocked_generation()
    with gen_patch as mock_generate, verify_patch as mock_verify:
        first = await client.post(
            f"/api/v1/applications/{application.id}/draft-answers",
            json={"question_text": "Why do you want to work here?"},
        )
        second = await client.post(
            f"/api/v1/applications/{application.id}/draft-answers",
            json={"question_text": "Why do you want to work here?"},
        )

    assert first.json()["id"] == second.json()["id"]
    mock_generate.assert_awaited_once()
    mock_verify.assert_awaited_once()


async def test_different_questions_on_the_same_application_are_independent(db, client) -> None:
    profile, job = await _make_profile_and_job(db)
    application = await get_or_create_application(profile, job, db)

    gen_patch, verify_patch = _mocked_generation()
    with gen_patch, verify_patch:
        first = await client.post(
            f"/api/v1/applications/{application.id}/draft-answers",
            json={"question_text": "Why do you want to work here?"},
        )
        second = await client.post(
            f"/api/v1/applications/{application.id}/draft-answers",
            json={"question_text": "What's your visa status?"},
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] != second.json()["id"]

    listed = await client.get(f"/api/v1/applications/{application.id}/draft-answers")
    assert {a["question_text"] for a in listed.json()} == {
        "Why do you want to work here?",
        "What's your visa status?",
    }


async def test_create_draft_answer_404s_for_unknown_application(client) -> None:
    response = await client.post(
        "/api/v1/applications/999999/draft-answers",
        json={"question_text": "Anything?"},
    )

    assert response.status_code == 404


async def test_list_draft_answers_404s_for_unknown_application(client) -> None:
    response = await client.get("/api/v1/applications/999999/draft-answers")

    assert response.status_code == 404


async def test_list_draft_answers_is_empty_for_a_fresh_application(db, client) -> None:
    profile, job = await _make_profile_and_job(db)
    application = await get_or_create_application(profile, job, db)

    response = await client.get(f"/api/v1/applications/{application.id}/draft-answers")

    assert response.status_code == 200
    assert response.json() == []
