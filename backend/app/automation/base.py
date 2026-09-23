import re
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any, Literal, TypedDict

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Frame, Locator, Page

# Where the fields actually live. Usually the page itself; on a company's own
# careers site it is the ATS form they embed in an iframe. Every fill step works
# against either — only the object owning the locators differs.
FormContext = Page | Frame

FillStatus = Literal["filled", "captcha_required", "form_not_found"]


class FillResult(TypedDict):
    status: FillStatus
    filled_fields: dict[str, str]
    skipped_fields: list[str]
    screenshot: bytes | None


class FillPayload(TypedDict):
    """What fill() reads out of the loosely-typed `payload: dict[str, Any]` the
    ATSAdapter interface specifies. Documents the real shape without widening
    that interface — different platforms need different things from it.
    """

    first_name: str
    last_name: str
    email: str
    phone: str | None
    location: str | None
    linkedin_url: str | None
    portfolio_url: str | None
    resume_bytes: bytes | None
    resume_filename: str
    # Called once per custom question actually found on the live form — the
    # question text is only known once the real page is open, so it can't be
    # precomputed into the payload the way the core fields can. The second
    # argument is the field's own character limit (None when it sets none), so
    # the answer can be written to fit rather than cut off by the browser.
    answer_question: Callable[[str, int | None], Awaitable[str]]
    # Same idea for dropdowns, but the caller also gets the option list this
    # specific form offers, and returns one of them (or None to leave it for the
    # human). Separate from answer_question because a dropdown cannot accept
    # free text at all — the choice has to come from the list or not happen.
    choose_option: Callable[[str, list[str]], Awaitable[str | None]]


# A question asking the candidate to accept a policy, not to answer something
# about themselves — e.g. "Privacy Notice Acknowledgement". Found live: the
# generator will happily draft "I acknowledge and agree..." text for one of
# these, but consenting to a company's data-processing terms is the candidate's
# own decision, not one to make on their behalf. Shared by every adapter, since
# the reasoning has nothing to do with which ATS is rendering the question.
CONSENT_QUESTION_PATTERN = re.compile(
    r"acknowledg|privacy notice|\bconsent\b|terms and conditions|\bi agree\b|gdpr",
    re.IGNORECASE,
)

# Hosts that serve a challenge instead of the page when they decide a visitor is
# automated. Found live on SmartRecruiters, which hands back a DataDome wall
# from geo.captcha-delivery.com rather than the application form — none of the
# recaptcha/hcaptcha markers appear, so without this a fill would report an
# empty form rather than a wall only a human can clear.
#
# Each entry is specific enough to mean "a challenge is being served": the bare
# word "cloudflare" would match cdnjs.cloudflare.com on any page that loads a
# library from it, and call every one of them a CAPTCHA.
BOT_WALL_HOSTS = (
    "captcha-delivery.com",
    "datadome",
    "perimeterx",
    "px-cloud",
    "challenges.cloudflare.com",
)

CAPTCHA_SELECTOR = ", ".join(
    [
        "iframe[src*='recaptcha']",
        "iframe[src*='hcaptcha']",
        "#g-recaptcha-response",
        # Matched in the markup as well as by frame URL: a challenge iframe that
        # has not loaded yet (or was blocked) still shows up here.
        *(f"iframe[src*='{host}']" for host in BOT_WALL_HOSTS),
    ]
)


def is_consent_question(question_text: str) -> bool:
    return bool(CONSENT_QUESTION_PATTERN.search(question_text))


async def max_length_of(field: Locator) -> int | None:
    """The field's own character limit, or None when it declares none.

    Measured across six live Greenhouse postings: 20 of 63 text fields carry
    maxlength=255 — every single-line question input — while the answers
    generated for them average 154 characters and one in ten runs past 255.
    The browser silently keeps the first 255, so an answer that does not know
    the limit ends mid-word on the submitted form.
    """
    try:
        limit = await field.evaluate("el => el.maxLength")
    except PlaywrightError:
        return None
    # Chromium reports -1 for "no limit set".
    return limit if isinstance(limit, int) and limit > 0 else None


async def fill_text_answer(
    field: Locator,
    question_text: str,
    answer_question: Callable[[str, int | None], Awaitable[str]],
    filled: dict[str, str],
    skipped: list[str],
    text_fills: list[tuple[str, Locator, str]],
) -> None:
    """Answer one free-text question, within the field's own limit.

    The limit is passed to the caller so the answer can be written to fit, and
    enforced here as well: an answer that still does not fit is never written
    at all. Writing it would let the browser cut it off mid-sentence, and the
    read-back sweep would then have to notice and undo that after the fact.
    Every adapter answers free text the same way, so it lives here once.
    """
    limit = await max_length_of(field)
    answer = await answer_question(question_text, limit)
    if limit is not None and len(answer) > limit:
        skipped.append(question_text)
        return

    await field.fill(answer)
    filled[question_text] = answer
    text_fills.append((question_text, field, answer))


async def file_is_attached(form: FormContext, locator: Locator, filename: str) -> bool:
    """Whether the form really has the file, by either of the two ways it shows.

    The obvious signal is the input still holding it, and on a plain
    <input type=file> that is the whole story. It is not on Greenhouse: measured
    live, once its uploader hydrates it takes the file and removes the input
    element from the DOM altogether, rendering the name as a chip instead. So
    the input is not merely empty there, it is *gone* — asking it anything waits
    out the full locator timeout and then reports a missing resume over a form
    that visibly has one. That is how the first version of this check went
    wrong, and it cost thirty seconds a call while doing it.

    Hence both signals, and count() before evaluate() so a vanished input is a
    fast no rather than a timeout.
    """
    try:
        if await locator.count() > 0 and await locator.evaluate(
            "el => Boolean(el.files && el.files.length)"
        ):
            return True
        return await form.get_by_text(filename, exact=False).count() > 0
    except PlaywrightError:
        return False


async def confirm_file_fill(
    page: Page,
    form: FormContext,
    file_fills: list[tuple[str, Locator, dict]],
    filled: dict[str, str],
    skipped: list[str],
    settle_ms: int,
) -> None:
    """The file-input half of the read-back sweep every adapter runs.

    Same reasoning as the text one: re-attach what the form dropped, and stop
    claiming anything it still will not hold. A resume reported as attached
    over a form showing an empty upload control is the worst version of this
    failure, because it is the field a reviewer is least likely to re-check.
    """
    for key, locator, file_payload in file_fills:
        filename = str(file_payload["name"])
        if await file_is_attached(form, locator, filename):
            continue

        try:
            await locator.set_input_files(file_payload)
        except PlaywrightError:
            pass
        else:
            await page.wait_for_timeout(settle_ms)
            if await file_is_attached(form, locator, filename):
                continue

        filled.pop(key, None)
        skipped.append(key)


async def clear_text_field(locator: Locator) -> None:
    """Empty a field whose value is about to be reported as skipped.

    A fragment is worse than nothing. Found live on a Greenhouse question with
    maxlength=255 answered in 301 characters: the browser kept the first 255,
    so reading the value back disagreed with what was written and the field was
    demoted to skipped — while the form still showed half a sentence, ending
    mid-word, that a reviewer trusting the "skipped" label would submit without
    ever looking at it.

    Every adapter demotes a write it cannot confirm, so every adapter has to
    undo one too; the reasoning has nothing to do with which ATS is rendering
    the field.
    """
    try:
        await locator.fill("")
    except PlaywrightError:
        # A field that cannot even be cleared (detached, disabled, replaced by a
        # re-render) is one nothing can be claimed about either way.
        pass


async def has_captcha(page: Page, form: FormContext | None = None) -> bool:
    """True if anything on this page is guarding submission with a CAPTCHA.

    Checked three ways because the widget moves around: on a hosted posting it
    is markup in the page, on an embedded one it can be markup inside the frame
    instead, and either way a live challenge shows up as a loaded
    recaptcha/hcaptcha frame even when the element that spawned it is somewhere
    the adapter is not looking.
    """
    for frame in page.frames:
        if "recaptcha" in frame.url or "hcaptcha" in frame.url:
            return True
        if any(host in frame.url for host in BOT_WALL_HOSTS):
            return True
    if await page.locator(CAPTCHA_SELECTOR).count() > 0:
        return True
    return form is not None and form is not page and await form.locator(CAPTCHA_SELECTOR).count() > 0


class ATSAdapter(ABC):
    """Interface every ATS-specific form-filling adapter must implement.

    No implementation ever clicks submit. That is the human-approval gate
    MVP.md requires, not a step an adapter is allowed to take on its own:
    fill() returns the filled state and a screenshot for a human to review.
    """

    @abstractmethod
    async def matches(self, application_url: str) -> bool:
        """Return True if this adapter knows how to handle the given URL."""

    @abstractmethod
    async def fill(self, application_url: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Fill the application form and return the resulting field state for review."""
