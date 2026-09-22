from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from app.automation.adapters.ashby import AshbyFormAdapter

FIXTURE = (
    Path(__file__).parent.parent / "fixtures" / "ats_snapshots" / "ashby_tekion_application.html"
)

# Captured 2026-09-22 from a live posting. Ashby renders questions as controls
# the other adapters never met: single checkboxes standing in for yes/no, and
# radio groups whose options are label[for=...] elements.
EXPECTED_CHECKBOX_QUESTIONS = {
    "Have you been in your current role >1 year?",
    "Are you currently authorized to work in the United States?",
}
EXPECTED_TEXT_QUESTIONS = {"Current Manager", "Current Department Head"}
TRAVEL_QUESTION = "Willingness to Travel"
TRAVEL_OPTIONS = ["Not Willing to Travel", "0-25%", "25-50%", "50-75%", "75-100%"]


@pytest.fixture
async def page():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()
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


async def test_matches_ashby_hosted_postings_only() -> None:
    adapter = AshbyFormAdapter()

    assert await adapter.matches("https://jobs.ashbyhq.com/tekion/abc-123") is True
    assert await adapter.matches("https://ashbyhq.com/x/1") is True

    assert await adapter.matches("https://jobs.lever.co/acme/1") is False
    assert await adapter.matches("https://notashbyhq.com/x/1") is False


async def test_fills_the_core_fields(page) -> None:
    """Ashby gives its own fields stable ids and everything else a per-job
    UUID, so phone is found by input type rather than by name.
    """
    await page.set_content(FIXTURE.read_text(encoding="utf-8"))
    adapter = AshbyFormAdapter()

    result = await adapter._fill_page(page, make_payload())

    assert result["filled_fields"]["#_systemfield_name"] == "Ada Lovelace"
    assert result["filled_fields"]["#_systemfield_email"] == "ada@example.dev"
    assert result["filled_fields"]['input[type="tel"]'] == "555-0100"
    assert await page.locator("#_systemfield_name").input_value() == "Ada Lovelace"


async def test_answers_a_radio_group_from_its_own_option_labels(page) -> None:
    await page.set_content(FIXTURE.read_text(encoding="utf-8"))
    adapter = AshbyFormAdapter()
    offered: dict[str, list[str]] = {}

    async def recording_choice(question: str, options: list[str]) -> str:
        offered[question] = options
        return options[-1] if question == TRAVEL_QUESTION else options[0]

    result = await adapter._fill_page(page, make_payload(choose_option=recording_choice))

    assert offered[TRAVEL_QUESTION] == TRAVEL_OPTIONS
    assert result["filled_fields"][TRAVEL_QUESTION] == "75-100%"
    # the choice really landed on the form, not just in the report
    checked = await page.locator('input[type="radio"]:checked').count()
    assert checked >= 1


async def test_a_checkbox_question_is_asked_as_yes_or_no(page) -> None:
    """A lone checkbox is a yes/no question wearing a different control, so the
    caller answers the question rather than being asked whether to tick a box.
    """
    await page.set_content(FIXTURE.read_text(encoding="utf-8"))
    adapter = AshbyFormAdapter()
    offered: dict[str, list[str]] = {}

    async def recording_choice(question: str, options: list[str]) -> str:
        offered[question] = options
        return "Yes"

    result = await adapter._fill_page(page, make_payload(choose_option=recording_choice))

    for question in EXPECTED_CHECKBOX_QUESTIONS:
        assert offered[question] == ["Yes", "No"]
        assert result["filled_fields"][question] == "Yes"


async def test_answering_no_leaves_the_checkbox_clear(page) -> None:
    """"No" is already what an unticked box submits, so it is recorded as the
    answer without touching the control.
    """
    await page.set_content(FIXTURE.read_text(encoding="utf-8"))
    adapter = AshbyFormAdapter()

    async def always_no(question: str, options: list[str]) -> str:
        return "No" if options == ["Yes", "No"] else options[0]

    result = await adapter._fill_page(page, make_payload(choose_option=always_no))

    for question in EXPECTED_CHECKBOX_QUESTIONS:
        assert result["filled_fields"][question] == "No"
    assert await page.locator('input[type="checkbox"]:checked').count() == 0


async def test_answers_the_free_text_questions(page) -> None:
    await page.set_content(FIXTURE.read_text(encoding="utf-8"))
    adapter = AshbyFormAdapter()
    asked: list[str] = []

    async def recording_answer(question: str) -> str:
        asked.append(question)
        return f"ANSWER[{question}]"

    result = await adapter._fill_page(page, make_payload(answer_question=recording_answer))

    for question in EXPECTED_TEXT_QUESTIONS:
        assert question in asked
        assert result["filled_fields"][question] == f"ANSWER[{question}]"


async def test_the_marketing_consent_radios_are_never_answered(page) -> None:
    """Ashby's opt-in sits inside the Phone Number entry, so the question text
    above it reads "Phone Number" and says nothing about consent — only the
    radio labels do. It is refused by name for exactly that reason.
    """
    await page.set_content(FIXTURE.read_text(encoding="utf-8"))
    adapter = AshbyFormAdapter()

    await adapter._fill_page(page, make_payload())

    consent = page.locator('input[name="communicationConsent"]')
    assert await consent.count() > 0
    assert await page.locator('input[name="communicationConsent"]:checked').count() == 0


async def test_an_option_the_form_never_offered_is_refused(page) -> None:
    await page.set_content(FIXTURE.read_text(encoding="utf-8"))
    adapter = AshbyFormAdapter()

    async def hallucinate(question: str, options: list[str]) -> str:
        return "Somewhere between never and always"

    result = await adapter._fill_page(page, make_payload(choose_option=hallucinate))

    assert TRAVEL_QUESTION in result["skipped_fields"]
    assert await page.locator('input[type="radio"]:checked').count() == 0


async def test_uploads_the_resume(page) -> None:
    await page.set_content(FIXTURE.read_text(encoding="utf-8"))
    adapter = AshbyFormAdapter()

    result = await adapter._fill_page(page, make_payload())

    assert result["filled_fields"]["#_systemfield_resume"] == "ada-resume.pdf"


async def test_detects_the_recaptcha_on_the_fixture(page) -> None:
    await page.set_content(FIXTURE.read_text(encoding="utf-8"))
    adapter = AshbyFormAdapter()

    result = await adapter._fill_page(page, make_payload())

    assert result["status"] == "captcha_required"


async def test_the_submit_button_is_left_untouched(page) -> None:
    await page.set_content(FIXTURE.read_text(encoding="utf-8"))
    submit = page.locator("button:has-text('Submit Application')")
    assert await submit.count() >= 1
    was_disabled = await submit.first.is_disabled()

    adapter = AshbyFormAdapter()
    await adapter._fill_page(page, make_payload())

    assert await submit.first.is_disabled() == was_disabled


async def test_form_not_found_without_a_form_or_apply_trigger(page) -> None:
    await page.set_content("<html><body><h1>404</h1></body></html>")
    adapter = AshbyFormAdapter()

    result = await adapter._fill_page(page, make_payload())

    assert result["status"] == "form_not_found"


async def test_a_bot_wall_counts_as_a_captcha(page) -> None:
    """Found live on SmartRecruiters: instead of the form it hands back a
    DataDome challenge from geo.captcha-delivery.com, which carries none of the
    recaptcha markers. Without recognising it the fill would report an empty
    form rather than a wall only a human can clear.
    """
    from app.automation.base import has_captcha

    await page.set_content(
        "<html><body><iframe "
        "src='https://geo.captcha-delivery.com/captcha/?initialCid=x'></iframe></body></html>"
    )

    assert await has_captcha(page) is True
