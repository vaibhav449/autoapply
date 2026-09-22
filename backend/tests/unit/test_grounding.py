from app.models.profile import Profile
from app.services.tailoring.grounding import (
    VERIFICATION_SYSTEM_PROMPT,
    grounding_source,
)


def make_profile(**overrides) -> Profile:
    fields = {
        "id": 1,
        "name": "Ada Lovelace",
        "email": "ada@example.dev",
        "resume_text": "Backend engineer.",
        "years_experience": 1.0,
    }
    profile = Profile(**{**fields, **overrides})
    profile.projects = []
    return profile


def test_the_grounding_source_includes_what_the_candidate_supplied_directly() -> None:
    """The generator is told to use the structured fields, so a verifier that
    only sees resume prose flags the candidate's own details as unsupported.
    Measured before this was fixed: a LinkedIn URL the candidate typed in came
    back flagged as an unverified claim.
    """
    source = grounding_source(
        make_profile(
            location="Raichur, Karnataka, India",
            linkedin_url="https://linkedin.com/in/example",
            expected_ctc="12 LPA",
        )
    )

    assert "Raichur, Karnataka, India" in source
    assert "https://linkedin.com/in/example" in source
    assert "12 LPA" in source
    # and still the resume itself
    assert "Backend engineer." in source


def test_the_verification_prompt_spares_the_four_things_that_are_not_claims() -> None:
    """Each of these was flagged on a real application. None is a claim that
    could be unsupported, and together they were most of the warnings on the
    review screen — which is how a flag stops meaning anything.
    """
    prompt = VERIFICATION_SYSTEM_PROMPT

    assert "does NOT have something" in prompt  # a denial
    assert "about the source material itself" in prompt  # "my resume does not specify"
    assert "details the candidate provided" in prompt  # what they supplied directly
    assert "N/A" in prompt  # filler with no factual content

    # and it still asks for real fabrications
    assert "NOT supported" in prompt
