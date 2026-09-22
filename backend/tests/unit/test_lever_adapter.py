from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from app.automation.adapters.lever import LeverFormAdapter

FIXTURE = (
    Path(__file__).parent.parent
    / "fixtures"
    / "ats_snapshots"
    / "lever_cin7_revenue_enablement.html"
)

# The real posting's questions, captured 2026-09-22. Lever renders these as
# native <select> and <textarea> under cards[<uuid>][fieldN], which is why the
# dropdowns here can be answered at all — on Greenhouse the equivalent controls
# are react-select widgets that ignore .fill() entirely.
EXPECTED_SELECT_QUESTIONS = {
    "Do you currently require sponsorship for employment in the United States?",
    "In the future, will you require sponsorship for employment in the United States?",
}
EXPECTED_TEXT_QUESTIONS = {
    "What is your desired salary?",
    "Where are you currently located?",
}


@pytest.fixture
async def page():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()
        # Offline and deterministic: the snapshot still references the real
        # site's assets, and nothing here should reach the network.
        await page.route("**/*", lambda route: route.abort())
        yield page
        await browser.close()


async def fake_answer(question: str) -> str:
    return f"ANSWER[{question}]"


async def fake_choice(question: str, options: list[str]) -> str:
    return options[0]


def make_payload(**overrides):
    payload = {
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": "ada@example.dev",
        "phone": "555-0100",
        "location": "Bengaluru",
        "linkedin_url": "https://linkedin.com/in/ada",
        "portfolio_url": "https://github.com/ada",
        "resume_bytes": b"%PDF-1.4 fake",
        "resume_filename": "ada-resume.pdf",
        "answer_question": fake_answer,
        "choose_option": fake_choice,
    }
    payload.update(overrides)
    return payload


async def test_matches_lever_hosted_postings_only() -> None:
    adapter = LeverFormAdapter()

    assert await adapter.matches("https://jobs.lever.co/cin7/abc-123") is True
    assert await adapter.matches("https://jobs.eu.lever.co/acme/1") is True

    assert await adapter.matches("https://job-boards.greenhouse.io/capco/jobs/1") is False
    assert await adapter.matches("https://example.com/jobs?src=lever.co") is False
    # a host that merely ends in the same letters is not Lever
    assert await adapter.matches("https://notlever.co/jobs/1") is False


async def test_fills_the_core_fields_from_the_real_fixture(page) -> None:
    """Lever keys fields by name rather than id, and takes one full name where
    Greenhouse takes a first/last pair.
    """
    await page.set_content(FIXTURE.read_text(encoding="utf-8"))
    adapter = LeverFormAdapter()

    result = await adapter._fill_page(page, make_payload())

    assert result["filled_fields"]['input[name="name"]'] == "Ada Lovelace"
    assert result["filled_fields"]['input[name="email"]'] == "ada@example.dev"
    assert result["filled_fields"]['input[name="phone"]'] == "555-0100"
    assert await page.locator('input[name="name"]').input_value() == "Ada Lovelace"


async def test_fills_the_link_fields_from_the_profile_directly(page) -> None:
    """Lever asks for these outright, so they come from the profile rather than
    costing an LLM call through a custom question.
    """
    await page.set_content(FIXTURE.read_text(encoding="utf-8"))
    adapter = LeverFormAdapter()

    result = await adapter._fill_page(page, make_payload())

    assert result["filled_fields"]['input[name="urls[LinkedIn]"]'] == "https://linkedin.com/in/ada"
    assert result["filled_fields"]['input[name="urls[GitHub]"]'] == "https://github.com/ada"


async def test_answers_the_real_free_text_questions(page) -> None:
    await page.set_content(FIXTURE.read_text(encoding="utf-8"))
    adapter = LeverFormAdapter()
    asked: list[str] = []

    async def recording_answer(question: str) -> str:
        asked.append(question)
        return f"ANSWER[{question}]"

    result = await adapter._fill_page(page, make_payload(answer_question=recording_answer))

    assert set(asked) == EXPECTED_TEXT_QUESTIONS
    for question in EXPECTED_TEXT_QUESTIONS:
        assert result["filled_fields"][question] == f"ANSWER[{question}]"


async def test_answers_native_select_questions_from_their_own_options(page) -> None:
    """The payoff of Lever's plain <select>: the options are readable without
    opening anything, so a question dropdown is answerable rather than skipped.
    """
    await page.set_content(FIXTURE.read_text(encoding="utf-8"))
    adapter = LeverFormAdapter()
    offered: dict[str, list[str]] = {}

    async def recording_choice(question: str, options: list[str]) -> str:
        offered[question] = options
        return "No"

    result = await adapter._fill_page(page, make_payload(choose_option=recording_choice))

    assert set(offered) == EXPECTED_SELECT_QUESTIONS
    for question in EXPECTED_SELECT_QUESTIONS:
        # the placeholder is not an answer and must not be offered as one
        assert offered[question] == ["Yes", "No"]
        assert result["filled_fields"][question] == "No"


async def test_a_declined_dropdown_is_left_for_the_human(page) -> None:
    await page.set_content(FIXTURE.read_text(encoding="utf-8"))
    adapter = LeverFormAdapter()

    async def decline(question: str, options: list[str]) -> None:
        return None

    result = await adapter._fill_page(page, make_payload(choose_option=decline))

    for question in EXPECTED_SELECT_QUESTIONS:
        assert question in result["skipped_fields"]
        assert question not in result["filled_fields"]


async def test_an_option_the_form_never_offered_is_refused(page) -> None:
    """Same gate as every other adapter: whatever the caller returns is checked
    against what this form actually lists, so a hallucinated value cannot be
    selected.
    """
    await page.set_content(FIXTURE.read_text(encoding="utf-8"))
    adapter = LeverFormAdapter()

    async def hallucinate(question: str, options: list[str]) -> str:
        return "Maybe, ask me later"

    result = await adapter._fill_page(page, make_payload(choose_option=hallucinate))

    for question in EXPECTED_SELECT_QUESTIONS:
        assert question in result["skipped_fields"]


async def test_self_identification_is_never_touched(page) -> None:
    """EEO lives under its own eeo[...] namespace here rather than looking like
    any other question, so it is left alone by construction — nothing legally
    sensitive gets guessed on the candidate's behalf.
    """
    await page.set_content(FIXTURE.read_text(encoding="utf-8"))
    adapter = LeverFormAdapter()
    asked: list[str] = []

    async def recording_choice(question: str, options: list[str]) -> str:
        asked.append(question)
        return options[0]

    await adapter._fill_page(page, make_payload(choose_option=recording_choice))

    assert not any("gender" in q.lower() or "race" in q.lower() for q in asked)
    for field in ("eeo[gender]", "eeo[race]", "eeo[veteran]"):
        selected = await page.locator(f'[name="{field}"]').input_value()
        assert selected == "", f"{field} should be untouched, got {selected!r}"


async def test_the_template_field_is_not_mistaken_for_a_question(page) -> None:
    """cards[...][baseTemplate] carries the template id and shares its
    question's label, so without skipping it the same question is answered
    twice — once into a field that is not an answer at all.
    """
    await page.set_content(FIXTURE.read_text(encoding="utf-8"))
    adapter = LeverFormAdapter()
    asked: list[str] = []

    async def recording_answer(question: str) -> str:
        asked.append(question)
        return "x"

    await adapter._fill_page(page, make_payload(answer_question=recording_answer))

    assert len(asked) == len(set(asked)), f"a question was asked twice: {asked}"


async def test_uploads_the_resume(page) -> None:
    await page.set_content(FIXTURE.read_text(encoding="utf-8"))
    adapter = LeverFormAdapter()

    result = await adapter._fill_page(page, make_payload())

    assert result["filled_fields"]["resume"] == "ada-resume.pdf"


async def test_the_submit_button_is_left_untouched(page) -> None:
    await page.set_content(FIXTURE.read_text(encoding="utf-8"))
    submit = page.locator("button:has-text('Submit')")
    assert await submit.count() >= 1
    was_disabled = await submit.first.is_disabled()

    adapter = LeverFormAdapter()
    await adapter._fill_page(page, make_payload())

    assert await submit.first.is_disabled() == was_disabled


async def test_form_not_found_when_there_is_no_form_and_no_apply_trigger(page) -> None:
    await page.set_content("<html><body><h1>404</h1></body></html>")
    adapter = LeverFormAdapter()

    result = await adapter._fill_page(page, make_payload())

    assert result["status"] == "form_not_found"
    assert result["screenshot"] is None
