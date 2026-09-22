import re
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any, Literal, TypedDict

from playwright.async_api import Frame, Page

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
    # precomputed into the payload the way the core fields can.
    answer_question: Callable[[str], Awaitable[str]]
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

CAPTCHA_SELECTOR = "iframe[src*='recaptcha'], iframe[src*='hcaptcha'], #g-recaptcha-response"


def is_consent_question(question_text: str) -> bool:
    return bool(CONSENT_QUESTION_PATTERN.search(question_text))


async def has_captcha(page: Page, form: FormContext | None = None) -> bool:
    """True if anything on this page is guarding submission with a CAPTCHA.

    Checked three ways because the widget moves around: on a hosted posting it
    is markup in the page, on an embedded one it can be markup inside the frame
    instead, and either way a live challenge shows up as a loaded
    recaptcha/hcaptcha frame even when the element that spawned it is somewhere
    the adapter is not looking.
    """
    if any(("recaptcha" in frame.url or "hcaptcha" in frame.url) for frame in page.frames):
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
