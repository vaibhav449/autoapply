from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.models.job import Job as JobModel
from app.models.profile import Profile, ProfileProject
from app.services.tailoring.cover_letter import generate_cover_letter


def _fake_completion(text: str) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


async def test_generate_cover_letter_includes_resume_and_projects_in_prompt() -> None:
    profile = Profile(
        name="Ada Lovelace",
        email="ada@example.dev",
        resume_text="Backend engineer, 5 years, Python and Postgres.",
        years_experience=5.0,
        projects=[ProfileProject(title="Payments API", content_md="Built a Stripe-like API.")],
    )
    job = JobModel(
        external_id="1",
        source="greenhouse",
        title="Backend Engineer",
        company="Acme",
        location=None,
        url="https://example.test/1",
        description="We need someone who has built payment APIs.",
    )

    with patch(
        "app.services.tailoring.cover_letter.openai_client.chat.completions.create",
        new=AsyncMock(return_value=_fake_completion("Dear Acme, ...")),
    ) as mock_create:
        result = await generate_cover_letter(profile, job)

    assert result == "Dear Acme, ..."

    # the prompt actually sent must contain the real resume, project, and job content —
    # this is the whole grounding guarantee, worth asserting on directly, not just trusting it
    sent_messages = mock_create.await_args.kwargs["messages"]
    user_content = sent_messages[1]["content"]
    assert "Backend engineer, 5 years, Python and Postgres." in user_content
    assert "Payments API" in user_content
    assert "Built a Stripe-like API." in user_content
    assert "We need someone who has built payment APIs." in user_content


async def test_generate_cover_letter_works_with_no_projects() -> None:
    profile = Profile(
        name="No Projects Yet",
        email="noprojects@example.dev",
        resume_text="Frontend developer, 2 years.",
        years_experience=2.0,
        projects=[],
    )
    job = JobModel(
        external_id="2",
        source="greenhouse",
        title="Frontend Developer",
        company="Acme",
        location=None,
        url="https://example.test/2",
        description=None,
    )

    with patch(
        "app.services.tailoring.cover_letter.openai_client.chat.completions.create",
        new=AsyncMock(return_value=_fake_completion("A short pitch.")),
    ):
        result = await generate_cover_letter(profile, job)

    assert result == "A short pitch."
