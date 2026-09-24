from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from app.automation.adapters.greenhouse import GreenhouseFormAdapter, is_consent_question

FIXTURE = (
    Path(__file__).parent.parent / "fixtures" / "ats_snapshots" / "greenhouse_capco_ml_engineer.html"
)

# The real fixture's questions, captured 2026-09-18 from a live posting, split
# by what each field actually is (checked directly against the fixture, not
# assumed). Discovered live: 8 of these 14 are react-select comboboxes — an
# <input type="text"> in the DOM, but a search-to-filter box, not a place a
# free-text answer can actually land. This split doubles as a regression check:
# if Capco edits the form, either set goes stale and a test fails loudly rather
# than silently under- or mis-filling it.
EXPECTED_TEXT_QUESTIONS = {
    "How many years of experience you have as a ML Engineer?",
    "How many years of exp do you have with Python ?",
    "What is your CCTC in LPA ?",
    "What is your ECTC in LPA ?",
    (
        "Do you have experience working with Domestic / International stakeholders? "
        "Please specify the geographies and designation of stakeholders?"
    ),
    "How many years of exp do you have with React?",
    "Exp working with AWS?",
    "Current Location",
    "Preffered Location",
}

EXPECTED_COMBOBOX_QUESTIONS = {
    "What is your total years of experience",
    "How many years of experience you have in Banking/Financial Services Domain?",
    "What is your official Notice Period and LWD ?",
    "Do you have any offer in hand ?",
    "Capco Job Candidate Privacy Notice Acknowledgement",
}

EXPECTED_QUESTIONS = EXPECTED_TEXT_QUESTIONS | EXPECTED_COMBOBOX_QUESTIONS


@pytest.fixture
async def page():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()
        # The captured snapshot still references the real page's external assets
        # (reCAPTCHA, fonts, CDN scripts). These tests are meant to be offline
        # and deterministic, so nothing is allowed off the machine — without
        # this they quietly hit the network on every run and pay for it.
        await page.route("**/*", lambda route: route.abort())
        yield page
        await browser.close()


async def fake_answer(question: str, max_length: int | None) -> str:
    return f"ANSWER[{question}]"


async def fake_choice(question: str, options: list[str]) -> str | None:
    return options[0]


def make_payload(**overrides):
    payload = {
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": "ada@example.dev",
        "phone": "555-0100",
        "location": "Bengaluru",
        "resume_bytes": b"%PDF-1.4 fake",
        "resume_filename": "ada-resume.pdf",
        "answer_question": fake_answer,
        "choose_option": fake_choice,
    }
    payload.update(overrides)
    return payload


# A minimal stand-in for react-select's real contract, captured from the live
# posting: a text input with role=combobox, a "Toggle flyout" button beside it,
# and options that only exist in the DOM while the flyout is open, each with an
# id scoped by the input's own id. The captured fixture cannot cover this — it
# is a static snapshot with no JS, so nothing there ever opens.
REACT_SELECT_STUB = """
<html><body>
  <form>
    <label for="first_name">First Name*</label>
    <input id="first_name" type="text">

    <label for="question_1">How many years of experience do you have?*</label>
    <div class="select__control">
      <input id="question_1" type="text" role="combobox" aria-expanded="false">
      <button type="button" aria-label="Toggle flyout">v</button>
    </div>
    <div id="menu_1"></div>
  </form>
  <script>
    const OPTIONS = ['0-6 Years', '6-8 Years', 'Over 8 Years'];
    const input = document.getElementById('question_1');
    const menu = document.getElementById('menu_1');
    document.querySelector('button[aria-label="Toggle flyout"]').addEventListener('click', () => {
      const open = input.getAttribute('aria-expanded') === 'true';
      menu.innerHTML = '';
      if (!open) {
        OPTIONS.forEach((text, i) => {
          const div = document.createElement('div');
          div.id = 'react-select-question_1-option-' + i;
          div.setAttribute('role', 'option');
          div.textContent = text;
          div.addEventListener('click', () => {
            input.dataset.selected = text;
            menu.innerHTML = '';
            input.setAttribute('aria-expanded', 'false');
          });
          menu.appendChild(div);
        });
      }
      input.setAttribute('aria-expanded', open ? 'false' : 'true');
    });
  </script>
</body></html>
"""


async def test_fills_the_plain_core_fields_from_the_real_fixture(page) -> None:
    await page.set_content(FIXTURE.read_text(encoding="utf-8"))
    adapter = GreenhouseFormAdapter()

    result = await adapter._fill_page(page, make_payload())

    assert result["filled_fields"]["#first_name"] == "Ada"
    assert result["filled_fields"]["#last_name"] == "Lovelace"
    assert result["filled_fields"]["#email"] == "ada@example.dev"
    assert result["filled_fields"]["#phone"] == "555-0100"
    assert await page.locator("#first_name").input_value() == "Ada"


async def test_skips_the_location_combobox_when_its_search_cannot_run(page) -> None:
    """candidate-location is a react-select combobox, driven by typing and
    picking a geo suggestion. A static fixture has no JS, so no suggestion ever
    appears — and the honest result is an empty field reported as skipped,
    never text typed in that the widget would not treat as a selection.
    """
    await page.set_content(FIXTURE.read_text(encoding="utf-8"))
    adapter = GreenhouseFormAdapter()

    result = await adapter._fill_page(page, make_payload())

    assert "#candidate-location" in result["skipped_fields"]
    assert "#candidate-location" not in result["filled_fields"]
    assert await page.locator("#candidate-location").input_value() == ""


async def test_uploads_the_resume_file(page) -> None:
    await page.set_content(FIXTURE.read_text(encoding="utf-8"))
    adapter = GreenhouseFormAdapter()

    result = await adapter._fill_page(page, make_payload())

    assert result["filled_fields"]["#resume"] == "ada-resume.pdf"


async def test_skips_resume_upload_when_no_bytes_are_given(page) -> None:
    await page.set_content(FIXTURE.read_text(encoding="utf-8"))
    adapter = GreenhouseFormAdapter()

    result = await adapter._fill_page(page, make_payload(resume_bytes=None))

    assert "#resume" in result["skipped_fields"]
    assert "#resume" not in result["filled_fields"]


async def test_answers_every_real_free_text_question_on_the_fixture(page) -> None:
    """The regression check automation-plan.md calls for: if the real form's
    question set drifts, EXPECTED_TEXT_QUESTIONS goes stale and this fails
    loudly rather than silently under-filling the form.
    """
    await page.set_content(FIXTURE.read_text(encoding="utf-8"))
    adapter = GreenhouseFormAdapter()
    asked: list[str] = []

    async def recording_answer(question: str, max_length: int | None) -> str:
        asked.append(question)
        return f"ANSWER[{question}]"

    result = await adapter._fill_page(page, make_payload(answer_question=recording_answer))

    assert set(asked) == EXPECTED_TEXT_QUESTIONS
    for question in EXPECTED_TEXT_QUESTIONS:
        assert result["filled_fields"][question] == f"ANSWER[{question}]"


async def test_combobox_questions_are_never_answered_as_free_text(page) -> None:
    """Several of this form's questions are react-select comboboxes rendered as
    <input type="text">. Filling text into one selects nothing — the widget
    keeps showing "Select..." and the typed value never reaches what Greenhouse
    submits. They go through the option-picking path instead, which on this
    static fixture cannot open (no JS runs), so the honest result here is a
    skip — never a free-text answer, which is what this guards.
    """
    await page.set_content(FIXTURE.read_text(encoding="utf-8"))
    adapter = GreenhouseFormAdapter()
    asked: list[str] = []

    async def recording_answer(question: str, max_length: int | None) -> str:
        asked.append(question)
        return f"ANSWER[{question}]"

    result = await adapter._fill_page(page, make_payload(answer_question=recording_answer))

    assert set(asked).isdisjoint(EXPECTED_COMBOBOX_QUESTIONS)
    for question in EXPECTED_COMBOBOX_QUESTIONS:
        assert question in result["skipped_fields"]
        assert question not in result["filled_fields"]


async def test_detects_the_real_recaptcha_on_the_fixture(page) -> None:
    """This posting genuinely has reCAPTCHA Enterprise loaded — confirmed by
    inspecting the live page before this fixture was captured. The adapter
    must report it rather than claim a clean fill.
    """
    await page.set_content(FIXTURE.read_text(encoding="utf-8"))
    adapter = GreenhouseFormAdapter()

    result = await adapter._fill_page(page, make_payload())

    assert result["status"] == "captcha_required"


async def test_the_submit_button_is_left_untouched(page) -> None:
    """_fill_page has no code path that targets the submit button — confirmed
    here by checking it, not just filled fields, stays in its pre-fill state.
    A fixture has no live backend to submit to, so the stronger check (no
    submission request actually fired) belongs to the live test instead.
    """
    await page.set_content(FIXTURE.read_text(encoding="utf-8"))
    submit = page.locator("button:has-text('Submit application')")
    assert await submit.count() == 1
    was_disabled = await submit.is_disabled()

    adapter = GreenhouseFormAdapter()
    await adapter._fill_page(page, make_payload())

    assert await submit.count() == 1
    assert await submit.is_disabled() == was_disabled


async def test_matches_greenhouse_hosted_and_embedded_postings() -> None:
    """A branded careers site hands its application off to a Greenhouse form in
    an iframe — same form, same field ids, just framed — and links to it with
    Greenhouse's own gh_jid parameter. Checked live on stripe.com, whose apply
    page loads job-boards.greenhouse.io/embed/job_app. The host name is not the
    signal, since that is whichever company owns the site; gh_jid is.
    """
    adapter = GreenhouseFormAdapter()

    assert await adapter.matches("https://job-boards.greenhouse.io/capco/jobs/8152797") is True
    assert await adapter.matches("https://stripe.com/jobs/search?gh_jid=8007158") is True
    assert await adapter.matches("https://careers.example.com/roles/7?gh_jid=42&src=x") is True

    assert await adapter.matches("https://jobs.lever.co/acme/123") is False
    assert await adapter.matches("https://example.com/jobs?id=8007158") is False
    # not a Greenhouse domain just because the word appears in a path
    assert await adapter.matches("https://example.com/greenhouse.io/jobs/1") is False


async def test_fills_a_form_embedded_in_an_iframe(page) -> None:
    """Checked live on stripe.com: a branded careers page has no form of its own
    and loads job-boards.greenhouse.io/embed/job_app in an iframe instead. The
    fields inside carry the same ids, so the only thing that changes is which
    document owns them — routed here through a stub frame on that same URL.
    """
    embedded_form = (
        "<html><body><form>"
        "<label for='first_name'>First Name*</label><input id='first_name' type='text'>"
        "<label for='last_name'>Last Name*</label><input id='last_name' type='text'>"
        "<label for='email'>Email*</label><input id='email' type='text'>"
        "<label for='question_1'>Who is your current employer?*</label>"
        "<textarea id='question_1'></textarea>"
        "</form></body></html>"
    )
    # The frame must really live on the embed URL, since that is what the
    # adapter matches frames on — served here instead of fetched.
    await page.route(
        "**/embed/job_app*",
        lambda route: route.fulfill(status=200, content_type="text/html", body=embedded_form),
    )
    await page.set_content(
        "<html><body><h1>Careers</h1>"
        "<iframe src='https://job-boards.greenhouse.io/embed/job_app?for=acme&token=1'></iframe>"
        "</body></html>"
    )

    adapter = GreenhouseFormAdapter()
    result = await adapter._fill_page(page, make_payload())

    assert result["status"] != "form_not_found"
    assert result["filled_fields"]["#first_name"] == "Ada"
    assert result["filled_fields"]["#email"] == "ada@example.dev"
    assert result["filled_fields"]["Who is your current employer?"] == (
        "ANSWER[Who is your current employer?]"
    )

    frame = next(f for f in page.frames if "embed/job_app" in f.url)
    assert await frame.locator("#first_name").input_value() == "Ada"


async def test_a_field_wiped_by_late_hydration_is_refilled(page) -> None:
    """Measured live on an embedded form: the fields paint before React finishes
    hydrating, and hydration then empties anything written in that window —
    around two seconds in, with first_name, last_name and email silently
    cleared while later fields survived. .fill() reported success for all of
    them, so the result claimed six filled fields over a form showing three.

    The stub reproduces exactly that: one wipe, triggered by the first write.
    Driven by the input event rather than a timer on purpose — a timer races
    the fill on a fast machine and stops reproducing anything.
    """
    await page.set_content(
        """
        <html><body>
          <form>
            <label for="first_name">First Name*</label><input id="first_name" type="text">
            <label for="last_name">Last Name*</label><input id="last_name" type="text">
          </form>
          <script>
            const el = document.getElementById('first_name');
            window.__writes = 0;
            el.addEventListener('input', () => { window.__writes += 1; });
            // one reset, on the first write only, exactly like a hydration pass
            el.addEventListener('input', function once() {
              el.removeEventListener('input', once);
              el.value = '';
            });
          </script>
        </body></html>
        """
    )

    adapter = GreenhouseFormAdapter()
    result = await adapter._fill_page(page, make_payload())

    assert result["filled_fields"]["#first_name"] == "Ada"
    assert "#first_name" not in result["skipped_fields"]
    # and the claim is true of the form, not just of the return value
    assert await page.locator("#first_name").input_value() == "Ada"
    # the repair really ran — without this the test would pass just as well on
    # a stub that never wiped anything, proving nothing
    assert await page.evaluate("window.__writes") == 2


async def test_a_field_that_will_not_hold_a_value_is_reported_skipped(page) -> None:
    """The other half: when re-filling still does not stick, the field must stop
    being claimed as filled. Reporting a value the form does not have is the
    failure this whole sweep exists to prevent.
    """
    await page.set_content(
        """
        <html><body>
          <form>
            <label for="first_name">First Name*</label><input id="first_name" type="text">
          </form>
          <script>
            // refuses every write, synchronously, so there is no window in
            // which a reader could see the value and believe it stuck
            const el = document.getElementById('first_name');
            el.addEventListener('input', () => { el.value = ''; });
          </script>
        </body></html>
        """
    )

    adapter = GreenhouseFormAdapter()
    result = await adapter._fill_page(page, make_payload())

    assert "#first_name" not in result["filled_fields"]
    assert "#first_name" in result["skipped_fields"]


async def test_an_answer_cut_short_by_the_page_is_cleared_rather_than_left_half_written(
    page,
) -> None:
    """The safety net under the limit check below. Found live on a Capco
    question answered in 301 characters: the browser kept the first 255, the
    read-back demoted the field to skipped — and left half a sentence, ending
    mid-word, that a reviewer trusting the "skipped" label would have
    submitted. A fragment is worse than nothing: nothing is at least what
    "skipped" claims.

    A declared maxlength is now refused before anything is written, so this
    uses the case that check cannot see: a limit enforced by script, with no
    attribute to read.
    """
    limit = 20
    await page.set_content(
        f"""
        <html><body>
          <form>
            <label for="first_name">First Name*</label><input id="first_name" type="text">
            <label for="question_1">How many years with React?*</label>
            <input id="question_1" type="text">
          </form>
          <script>
            const el = document.getElementById('question_1');
            el.addEventListener('input', () => {{ el.value = el.value.slice(0, {limit}); }});
          </script>
        </body></html>
        """
    )
    long_answer = "x" * (limit + 40)

    adapter = GreenhouseFormAdapter()
    result = await adapter._fill_page(
        page, make_payload(answer_question=lambda question, max_length: _answer(long_answer))
    )

    question = "How many years with React?"
    assert question in result["skipped_fields"]
    assert question not in result["filled_fields"]
    # The claim and the form now agree: nothing there.
    assert await page.locator("#question_1").input_value() == ""


LIMITED_FIELD_STUB = """
<html><body>
  <form>
    <label for="first_name">First Name*</label><input id="first_name" type="text">
    <label for="question_1">How many years with React?*</label>
    <input id="question_1" type="text" maxlength="20">
    <label for="question_2">Tell us about yourself*</label>
    <textarea id="question_2"></textarea>
  </form>
  <script>
    window.__writes = 0;
    document.getElementById('question_1')
      .addEventListener('input', () => { window.__writes += 1; });
  </script>
</body></html>
"""


async def test_each_answer_is_asked_for_within_its_fields_own_limit(page) -> None:
    """Measured across six live Greenhouse postings: every single-line question
    input carries maxlength=255, while the answers generated for them run past
    that about one time in ten. The limit is handed to whoever writes the
    answer, so it can be written to fit instead of cut off.
    """
    await page.set_content(LIMITED_FIELD_STUB)
    offered: dict[str, int | None] = {}

    async def recording_answer(question: str, max_length: int | None) -> str:
        offered[question] = max_length
        return "short"

    adapter = GreenhouseFormAdapter()
    await adapter._fill_page(page, make_payload(answer_question=recording_answer))

    assert offered == {"How many years with React?": 20, "Tell us about yourself": None}


async def test_an_answer_that_still_does_not_fit_is_never_written(page) -> None:
    """Whatever the caller hands back, nothing longer than the field holds is
    typed into it — the browser would keep the first part and drop the rest.
    """
    await page.set_content(LIMITED_FIELD_STUB)

    async def too_long(question: str, max_length: int | None) -> str:
        return "x" * 60

    adapter = GreenhouseFormAdapter()
    result = await adapter._fill_page(page, make_payload(answer_question=too_long))

    question = "How many years with React?"
    assert question in result["skipped_fields"]
    assert question not in result["filled_fields"]
    assert await page.evaluate("window.__writes") == 0
    assert await page.locator("#question_1").input_value() == ""


async def test_an_answer_that_fits_is_written_whole(page) -> None:
    await page.set_content(LIMITED_FIELD_STUB)

    async def exactly_fits(question: str, max_length: int | None) -> str:
        return "y" * (max_length or 30)

    adapter = GreenhouseFormAdapter()
    result = await adapter._fill_page(page, make_payload(answer_question=exactly_fits))

    assert result["filled_fields"]["How many years with React?"] == "y" * 20
    assert await page.locator("#question_1").input_value() == "y" * 20


async def _answer(text: str) -> str:
    return text


async def test_a_resume_the_form_drops_stops_being_claimed(page) -> None:
    """Found live on a Capco posting: the run reported the resume attached
    while the form was still showing its Attach / Dropbox / Google Drive
    buttons — set_input_files() had succeeded and a later re-render emptied the
    input again, exactly the way one empties a text field. The resume is the
    field a reviewer is least likely to re-check by hand, so a false claim
    about it is the most expensive one this can make.
    """
    await page.set_content(
        """
        <html><body>
          <form>
            <label for="first_name">First Name*</label><input id="first_name" type="text">
            <input id="resume" type="file">
          </form>
          <script>
            // empties the input on every attach, like a re-render that resets
            // the control after the write has already reported success
            const el = document.getElementById('resume');
            window.__attaches = 0;
            el.addEventListener('change', () => { window.__attaches += 1; el.value = ''; });
          </script>
        </body></html>
        """
    )

    adapter = GreenhouseFormAdapter()
    result = await adapter._fill_page(page, make_payload())

    # It really was attempted twice — written, found missing, re-attached.
    assert await page.evaluate("window.__attaches") == 2
    assert "#resume" not in result["filled_fields"]
    assert "#resume" in result["skipped_fields"]


async def test_an_uploader_that_swallows_the_input_still_counts_as_attached(page) -> None:
    """What Greenhouse actually does once its uploader hydrates, measured live:
    it takes the file, removes the <input> from the DOM entirely, and renders
    the filename as a chip instead. Judging that by el.files alone reports a
    missing resume over a form that visibly has one — and waits out the full
    locator timeout on the vanished element to do it.
    """
    await page.set_content(
        """
        <html><body>
          <form>
            <label for="first_name">First Name*</label><input id="first_name" type="text">
            <input id="resume" type="file">
          </form>
          <script>
            const el = document.getElementById('resume');
            el.addEventListener('change', () => {
              const name = el.files[0].name;
              const chip = document.createElement('span');
              chip.textContent = name;
              el.parentNode.appendChild(chip);
              el.remove();            // the control is gone, the file is kept
            });
          </script>
        </body></html>
        """
    )

    adapter = GreenhouseFormAdapter()
    result = await adapter._fill_page(page, make_payload())

    assert await page.locator("#resume").count() == 0  # really did vanish
    assert result["filled_fields"]["#resume"] == "ada-resume.pdf"
    assert "#resume" not in result["skipped_fields"]


async def test_a_resume_that_sticks_is_still_reported_filled(page) -> None:
    """The other side of the sweep: a form that keeps the file must not have it
    demoted, or every fill would report a missing resume.
    """
    await page.set_content(
        """
        <html><body>
          <form>
            <label for="first_name">First Name*</label><input id="first_name" type="text">
            <input id="resume" type="file">
          </form>
        </body></html>
        """
    )

    adapter = GreenhouseFormAdapter()
    result = await adapter._fill_page(page, make_payload())

    assert result["filled_fields"]["#resume"] == "ada-resume.pdf"
    assert "#resume" not in result["skipped_fields"]


async def test_form_not_found_when_neither_the_form_nor_an_apply_trigger_exists(page) -> None:
    await page.set_content("<html><body><h1>404</h1></body></html>")
    adapter = GreenhouseFormAdapter()

    result = await adapter._fill_page(page, make_payload())

    assert result["status"] == "form_not_found"
    assert result["screenshot"] is None


async def test_picks_a_real_option_from_a_dropdown(page) -> None:
    await page.set_content(REACT_SELECT_STUB)
    adapter = GreenhouseFormAdapter()
    offered: list[list[str]] = []

    async def recording_choice(question: str, options: list[str]) -> str:
        offered.append(options)
        return "6-8 Years"

    result = await adapter._fill_page(page, make_payload(choose_option=recording_choice))

    question = "How many years of experience do you have?"
    # the option list came from the live widget, not from anything precomputed
    assert offered == [["0-6 Years", "6-8 Years", "Over 8 Years"]]
    assert result["filled_fields"][question] == "6-8 Years"
    # and the option was really clicked, not just reported
    assert await page.locator("#question_1").get_attribute("data-selected") == "6-8 Years"


async def test_a_declined_dropdown_is_left_for_the_human(page) -> None:
    """None means "the candidate's material cannot answer this" — an offer in
    hand, a notice period, a consent. A wrong pick on a real application is
    worse than an empty field the human fills in during review.
    """
    await page.set_content(REACT_SELECT_STUB)
    adapter = GreenhouseFormAdapter()

    async def decline(question: str, options: list[str]) -> None:
        return None

    result = await adapter._fill_page(page, make_payload(choose_option=decline))

    question = "How many years of experience do you have?"
    assert question in result["skipped_fields"]
    assert question not in result["filled_fields"]
    assert await page.locator("#question_1").get_attribute("data-selected") is None


async def test_an_option_the_form_never_offered_is_refused(page) -> None:
    """The hard gate: whatever the caller returns is checked against the list
    this form actually rendered, so a hallucinated value cannot reach the form
    at all — the worst case is an honest skip.
    """
    await page.set_content(REACT_SELECT_STUB)
    adapter = GreenhouseFormAdapter()

    async def hallucinate(question: str, options: list[str]) -> str:
        return "12-15 Years"

    result = await adapter._fill_page(page, make_payload(choose_option=hallucinate))

    question = "How many years of experience do you have?"
    assert question in result["skipped_fields"]
    assert await page.locator("#question_1").get_attribute("data-selected") is None


async def test_a_consent_question_is_never_offered_to_the_option_picker(page) -> None:
    """A single-option "Acknowledge" dropdown is exactly the shape the picker
    handles well, which is why the consent check has to come first: consenting
    to a company's policy stays the candidate's own decision.
    """
    await page.set_content(
        REACT_SELECT_STUB.replace(
            "How many years of experience do you have?",
            "Capco Job Candidate Privacy Notice Acknowledgement",
        )
    )
    adapter = GreenhouseFormAdapter()
    asked: list[str] = []

    async def recording_choice(question: str, options: list[str]) -> str:
        asked.append(question)
        return options[0]

    result = await adapter._fill_page(page, make_payload(choose_option=recording_choice))

    assert asked == []
    assert "Capco Job Candidate Privacy Notice Acknowledgement" in result["skipped_fields"]
    assert await page.locator("#question_1").get_attribute("data-selected") is None


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Capco Job Candidate Privacy Notice Acknowledgement", True),
        ("I acknowledge the terms of this application", True),
        ("Do you consent to a background check?", True),
        ("Please review our GDPR notice and confirm", True),
        ("How many years of exp do you have with Python ?", False),
        ("What is your current location", False),
        ("Do you have any offer in hand ?", False),
    ],
)
def test_is_consent_question(question, expected) -> None:
    assert is_consent_question(question) is expected


async def test_a_consent_question_is_skipped_even_on_a_plain_text_field(page) -> None:
    """The real fixture's consent question happens to also be a combobox, which
    would mask a bug where consent detection only worked by accident. This
    uses a synthetic plain <textarea> instead, to prove the consent check
    itself — not the combobox check — is what's catching it.
    """
    await page.set_content(
        """
        <html><body>
          <form>
            <label for="first_name">First Name*</label>
            <input id="first_name" type="text">
            <label for="question_1">I acknowledge the Company Privacy Notice*</label>
            <textarea id="question_1"></textarea>
          </form>
        </body></html>
        """
    )
    adapter = GreenhouseFormAdapter()
    asked: list[str] = []

    async def recording_answer(question: str, max_length: int | None) -> str:
        asked.append(question)
        return "should never be called"

    result = await adapter._fill_page(page, make_payload(answer_question=recording_answer))

    assert asked == []
    assert "I acknowledge the Company Privacy Notice" in result["skipped_fields"]
    assert await page.locator("#question_1").input_value() == ""


async def test_a_question_handed_back_to_the_candidate_is_never_written(page) -> None:
    """No answer means the question is the candidate's own — a notice period
    left blank on their profile. The field stays empty and is reported
    skipped, instead of holding a sentence about the gap."""
    await page.set_content(LIMITED_FIELD_STUB)

    async def theirs_to_answer(question: str, max_length: int | None) -> str | None:
        return None

    adapter = GreenhouseFormAdapter()
    result = await adapter._fill_page(page, make_payload(answer_question=theirs_to_answer))

    question = "How many years with React?"
    assert question in result["skipped_fields"]
    assert question not in result["filled_fields"]
    assert await page.evaluate("window.__writes") == 0
