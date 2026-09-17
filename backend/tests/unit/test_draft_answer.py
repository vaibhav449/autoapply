from unittest.mock import AsyncMock, patch

import pytest

from app.models.job import Job as JobModel
from app.models.profile import Profile
from app.services.tailoring.draft_answer import generate_draft_answer


def make_profile() -> Profile:
    return Profile(
        id=1,
        name="Ada Lovelace",
        email="ada@example.dev",
        resume_text="Backend engineer with distributed systems experience.",
        years_experience=5.0,
    )


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
