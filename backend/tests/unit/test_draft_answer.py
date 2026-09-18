from unittest.mock import AsyncMock, patch

import pytest

from app.models.job import Job as JobModel
from app.models.profile import Profile
from app.services.tailoring.draft_answer import (
    CHOICE_SYSTEM_PROMPT,
    GENERATION_SYSTEM_PROMPT,
    choose_draft_option,
    generate_draft_answer,
)

EXPERIENCE_OPTIONS = ["0-6 Years", "6-8 Years", "8-10 Years", "Over 10 Years"]


def mock_completion(content: str | None):
    response = AsyncMock()
    response.choices = [AsyncMock(message=AsyncMock(content=content))]
    return AsyncMock(return_value=response)


def make_profile(**overrides) -> Profile:
    fields = {
        "id": 1,
        "name": "Ada Lovelace",
        "email": "ada@example.dev",
        "resume_text": "Backend engineer with distributed systems experience.",
        "years_experience": 5.0,
    }
    fields.update(overrides)
    return Profile(**fields)


def make_job() -> JobModel:
    return JobModel(
        id=1,
        external_id="x",
        source="greenhouse",
        title="Backend Engineer",
        company="acme",
        location=None,
        url="https://example.test/1",
        description="Build our core services.",
    )


async def test_generate_draft_answer_sends_the_question_and_job_context() -> None:
    fake_response = AsyncMock()
    fake_response.choices = [AsyncMock(message=AsyncMock(content="I'm excited because..."))]

    with patch(
        "app.services.tailoring.draft_answer.openai_client.chat.completions.create",
        new=AsyncMock(return_value=fake_response),
    ) as mock_create:
        content = await generate_draft_answer(
            make_profile(), make_job(), "Why do you want to work here?"
        )

    assert content == "I'm excited because..."
    sent = mock_create.await_args.kwargs["messages"][1]["content"]
    assert "Why do you want to work here?" in sent
    assert "Backend Engineer" in sent
    assert "acme" in sent
    assert "distributed systems" in sent


async def test_generate_draft_answer_sends_structured_location_and_experience() -> None:
    """Found live: the model conflated an internship employer's city
    ("Setubridge Technolabs, Ahmedabad") with the candidate's own location,
    because it only had unstructured resume prose to infer from. The
    structured profile.location field is now sent explicitly and marked
    authoritative so there's a reliable source to prefer instead.
    """
    fake_response = AsyncMock()
    fake_response.choices = [AsyncMock(message=AsyncMock(content="Answer."))]

    with patch(
        "app.services.tailoring.draft_answer.openai_client.chat.completions.create",
        new=AsyncMock(return_value=fake_response),
    ) as mock_create:
        await generate_draft_answer(
            make_profile(location="Raichur, Karnataka, India", years_experience=1.0),
            make_job(),
            "What is your current location?",
        )

    sent = mock_create.await_args.kwargs["messages"][1]["content"]
    assert "STRUCTURED PROFILE DATA" in sent
    assert "Raichur, Karnataka, India" in sent
    assert "Years of professional experience: 1" in sent


async def test_generate_draft_answer_handles_a_missing_location_gracefully() -> None:
    fake_response = AsyncMock()
    fake_response.choices = [AsyncMock(message=AsyncMock(content="Answer."))]

    with patch(
        "app.services.tailoring.draft_answer.openai_client.chat.completions.create",
        new=AsyncMock(return_value=fake_response),
    ) as mock_create:
        await generate_draft_answer(make_profile(location=None), make_job(), "Where are you based?")

    sent = mock_create.await_args.kwargs["messages"][1]["content"]
    assert "Location: not provided" in sent


async def test_generate_draft_answer_is_deterministic() -> None:
    """Cached permanently by ensure_draft_answer, so a sampled answer is stuck
    on the row forever — same reasoning as job-requirements extraction.
    """
    fake_response = AsyncMock()
    fake_response.choices = [AsyncMock(message=AsyncMock(content="Answer."))]

    with patch(
        "app.services.tailoring.draft_answer.openai_client.chat.completions.create",
        new=AsyncMock(return_value=fake_response),
    ) as mock_create:
        await generate_draft_answer(make_profile(), make_job(), "Anything?")

    assert mock_create.await_args.kwargs["temperature"] == 0


def test_generation_prompt_forbids_markdown() -> None:
    """Found live: the LLM wrote "[LinkedIn](https://...)" for a LinkedIn
    question, and Playwright typed that literal markdown syntax into the real
    plain-text form field — there is no renderer on the other end.
    """
    assert "plain text only" in GENERATION_SYSTEM_PROMPT
    assert "[link](url)" in GENERATION_SYSTEM_PROMPT


async def test_choose_draft_option_returns_the_picked_option() -> None:
    with patch(
        "app.services.tailoring.draft_answer.openai_client.chat.completions.create",
        new=mock_completion("0-6 Years"),
    ) as mock_create:
        choice = await choose_draft_option(
            make_profile(years_experience=1.0),
            make_job(),
            "What is your total years of experience",
            EXPERIENCE_OPTIONS,
        )

    assert choice == "0-6 Years"
    sent = mock_create.await_args.kwargs["messages"][1]["content"]
    # the real options the live form offered are what it chooses between
    for option in EXPERIENCE_OPTIONS:
        assert option in sent
    assert mock_create.await_args.kwargs["temperature"] == 0


def test_choice_prompt_treats_a_no_experience_option_as_answerable() -> None:
    """Found live: asked about Banking/Financial Services experience with
    "No/Limited Experience" on the list, the model declined — reading "the
    resume never mentions banking" as "I cannot answer". That option is exactly
    what a candidate without the experience should pick, so the absence is the
    answer, not a reason to leave the field blank.
    """
    assert "No/Limited Experience" in CHOICE_SYSTEM_PROMPT
    assert "its absence is the answer" in CHOICE_SYSTEM_PROMPT


async def test_choose_draft_option_returns_none_when_the_model_declines() -> None:
    """NONE is how the model says the resume genuinely cannot answer this — an
    offer in hand, a notice period. It must not become a guess.
    """
    with patch(
        "app.services.tailoring.draft_answer.openai_client.chat.completions.create",
        new=mock_completion("NONE"),
    ):
        choice = await choose_draft_option(
            make_profile(), make_job(), "Do you have any offer in hand ?", ["Yes", "No"]
        )

    assert choice is None


@pytest.mark.parametrize(
    "reply",
    [
        "12-15 Years",  # plausible, but this form never offered it
        "0-6 years",  # right option, wrong case — still not what the form has
        "I would say 0-6 Years",  # an answer wrapped in prose
        "",
    ],
)
async def test_choose_draft_option_refuses_anything_the_form_did_not_offer(reply) -> None:
    """The hard gate. A value that is not literally one of the form's options
    can never be clicked anyway, so treating it as a refusal is what keeps a
    hallucination from turning into a wrong answer on a real application.
    """
    with patch(
        "app.services.tailoring.draft_answer.openai_client.chat.completions.create",
        new=mock_completion(reply),
    ):
        choice = await choose_draft_option(
            make_profile(), make_job(), "Total years?", EXPERIENCE_OPTIONS
        )

    assert choice is None


async def test_choose_draft_option_returns_none_on_empty_content() -> None:
    with patch(
        "app.services.tailoring.draft_answer.openai_client.chat.completions.create",
        new=mock_completion(None),
    ):
        choice = await choose_draft_option(
            make_profile(), make_job(), "Total years?", EXPERIENCE_OPTIONS
        )

    assert choice is None


async def test_generate_draft_answer_raises_on_empty_content() -> None:
    fake_response = AsyncMock()
    fake_response.choices = [AsyncMock(message=AsyncMock(content=None))]

    with (
        patch(
            "app.services.tailoring.draft_answer.openai_client.chat.completions.create",
            new=AsyncMock(return_value=fake_response),
        ),
        pytest.raises(ValueError),
    ):
        await generate_draft_answer(make_profile(), make_job(), "Anything?")
