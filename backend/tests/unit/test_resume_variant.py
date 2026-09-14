from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.models.job import Job as JobModel
from app.models.profile import Profile, ProfileProject
from app.services.tailoring.resume_variant import (
    VerificationResult,
    generate_resume_variant,
    verify_grounding,
)


def _fake_completion(text: str) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


async def test_generate_resume_variant_includes_profile_role_and_samples_in_prompt() -> None:
    profile = Profile(
        name="Ada Lovelace",
        resume_text="Backend engineer, 5 years, Python and Postgres.",
        years_experience=5.0,
        projects=[ProfileProject(title="Payments API", content_md="Built a Stripe-like API.")],
    )
    sample_job = JobModel(
        external_id="1",
        source="greenhouse",
        title="Backend Engineer",
        company="Acme",
        location=None,
        url="https://example.test/1",
        description="Needs strong API design skills.",
    )

    with patch(
        "app.services.tailoring.resume_variant.openai_client.chat.completions.create",
        new=AsyncMock(return_value=_fake_completion("Tailored resume content.")),
    ) as mock_create:
        result = await generate_resume_variant(profile, "Backend Engineer", "emphasize APIs", [sample_job])

    assert result == "Tailored resume content."

    user_content = mock_create.await_args.kwargs["messages"][1]["content"]
    assert "Backend engineer, 5 years, Python and Postgres." in user_content
    assert "Payments API" in user_content
    assert "Backend Engineer" in user_content
    assert "emphasize APIs" in user_content
    assert "Needs strong API design skills." in user_content


async def test_verify_grounding_parses_structured_response() -> None:
    fake_result = VerificationResult(unverified_claims=["Kubernetes"])

    with patch(
        "app.services.tailoring.resume_variant.openai_client.chat.completions.parse",
        new=AsyncMock(
            return_value=SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(parsed=fake_result, refusal=None))]
            )
        ),
    ):
        result = await verify_grounding("generated text mentioning Kubernetes", "source text without it")

    assert result.unverified_claims == ["Kubernetes"]
