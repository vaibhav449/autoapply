import re
from collections.abc import Awaitable, Callable
from typing import Any, Literal, TypedDict

from playwright.async_api import Locator, Page, async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.automation.base import ATSAdapter

# How long to wait for the core name/email fields to appear before giving up —
# either they're already on the page, or an "Apply" click needs to reveal them.
REVEAL_TIMEOUT_MS = 8000

# react-select renders its option list only once the flyout is actually open.
# Found live: the very first toggle click on a freshly-loaded page is sometimes
# swallowed while hydration is still settling. That is a page-level, one-time
# condition, so only the first dropdown gets retries — once any dropdown on the
# page has opened, hydration is demonstrably done and a click that does nothing
# means the widget is not going to open at all. Opening is pure client-side
# state with no network call, so an attempt only needs long enough to rule out
# a swallowed click.
DROPDOWN_OPEN_ATTEMPTS = 3
DROPDOWN_OPEN_TIMEOUT_MS = 500
# The location suggestions do come from a lookup service, so they get a longer
# budget — but only once the widget has proved it is live by opening at all,
# which keeps a page whose JS never runs from costing the full wait.
LOCATION_OPEN_TIMEOUT_MS = 800
LOCATION_SEARCH_TIMEOUT_MS = 5000

_IS_EXPANDED = "id => document.getElementById(id)?.getAttribute('aria-expanded') === 'true'"

# A question asking the candidate to accept a policy, not to answer something
# about themselves — e.g. "Privacy Notice Acknowledgement". Found live: the
# generator will happily draft "I acknowledge and agree..." text for one of
# these, but consenting to a company's data-processing terms is the
# candidate's own decision, not one to make on their behalf. A module-level
# function (not adapter state) so a second ATS adapter can reuse it without
# duplicating the pattern.
CONSENT_QUESTION_PATTERN = re.compile(
    r"acknowledg|privacy notice|\bconsent\b|terms and conditions|\bi agree\b|gdpr",
    re.IGNORECASE,
)


def is_consent_question(question_text: str) -> bool:
    return bool(CONSENT_QUESTION_PATTERN.search(question_text))


class FillPayload(TypedDict):
    """What fill() reads out of the loosely-typed `payload: dict[str, Any]` the
    ATSAdapter interface specifies. Documents the real shape without widening
    that interface — it's typed as dict[str, Any] because different ATS
    platforms will eventually need different things in it.
    """

    first_name: str
    last_name: str
    email: str
    phone: str | None
    location: str | None
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


FillStatus = Literal["filled", "captcha_required", "form_not_found"]


class FillResult(TypedDict):
    status: FillStatus
    filled_fields: dict[str, str]
    skipped_fields: list[str]
    screenshot: bytes | None


# Greenhouse's own core fields carry stable ids across every job-boards.greenhouse.io
# posting — this is part of their platform, unlike the per-job custom questions
# below, which get a fresh numeric id every time a company edits their form.
CORE_FIELD_SELECTORS = {
    "first_name": "#first_name",
    "last_name": "#last_name",
    "email": "#email",
    "phone": "#phone",
    "location": "#candidate-location",
}


class GreenhouseFormAdapter(ATSAdapter):
    """Fills a Greenhouse-hosted application form.

    Never clicks the submit button under any circumstance — that is the
    human-approval gate MVP.md requires, not a step this class is allowed to
    take on its own. fill() returns the filled state (and a screenshot) for a
    human to review before anything is actually sent.
    """

    async def matches(self, application_url: str) -> bool:
        # Deliberately narrow: only greenhouse.io's own hosted pages have the
        # DOM shape this adapter was built against. A company's custom-branded
        # careers page that embeds Greenhouse via an API (e.g. stripe.com's own
        # career pages) is a structurally different form and not handled here.
        return "greenhouse.io" in application_url

    async def fill(self, application_url: str, payload: dict[str, Any]) -> dict[str, Any]:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch()
            try:
                page = await browser.new_page()
                await page.goto(application_url, wait_until="domcontentloaded", timeout=30000)
                return await self._fill_page(page, payload)
            finally:
                await browser.close()

    async def _fill_page(self, page: Page, payload: dict[str, Any]) -> FillResult:
        if not await self._reveal_form(page):
            return FillResult(status="form_not_found", filled_fields={}, skipped_fields=[], screenshot=None)

        filled: dict[str, str] = {}
        skipped: list[str] = []

        await self._fill_core_fields(page, payload, filled, skipped)
        await self._fill_custom_questions(page, payload, filled, skipped)

        # Checked after filling, not before: a fully-filled form is what makes
        # the pending_captcha review screen useful — the human should see every
        # answer already in place and only need to solve the one checkbox.
        status: FillStatus = "captcha_required" if await self._has_captcha(page) else "filled"
        screenshot = await page.screenshot(full_page=True)

        return FillResult(status=status, filled_fields=filled, skipped_fields=skipped, screenshot=screenshot)

    async def _reveal_form(self, page: Page) -> bool:
        if await self._wait_for_first_name(page):
            return True

        apply = page.locator("a:has-text('Apply'), button:has-text('Apply')").first
        if await apply.count() == 0:
            return False
        await apply.click()
        return await self._wait_for_first_name(page)

    async def _wait_for_first_name(self, page: Page) -> bool:
        try:
            await page.locator(CORE_FIELD_SELECTORS["first_name"]).wait_for(timeout=REVEAL_TIMEOUT_MS)
            return True
        except PlaywrightTimeoutError:
            return False

    async def _fill_core_fields(
        self, page: Page, payload: dict[str, Any], filled: dict[str, str], skipped: list[str]
    ) -> None:
        for field, selector in CORE_FIELD_SELECTORS.items():
            value = payload.get(field)
            locator = page.locator(selector)
            if not value or await locator.count() == 0:
                skipped.append(selector)
                continue
            if await self._is_combobox(locator):
                # candidate-location is a react-select combobox on this platform,
                # not a plain text field — .fill() alone writes text the widget
                # never treats as a real selection, so it has to be driven as a
                # search-and-pick instead.
                selected = await self._select_location(page, locator, str(value))
                if selected is None:
                    skipped.append(selector)
                else:
                    filled[selector] = selected
                continue
            await locator.fill(str(value))
            filled[selector] = str(value)

        resume_bytes = payload.get("resume_bytes")
        resume_field = page.locator("#resume")
        if resume_bytes and await resume_field.count() > 0:
            await resume_field.set_input_files(
                {
                    "name": payload.get("resume_filename") or "resume.pdf",
                    "mimeType": "application/pdf",
                    "buffer": resume_bytes,
                }
            )
            filled["#resume"] = payload.get("resume_filename") or "resume.pdf"
        else:
            skipped.append("#resume")

    async def _fill_custom_questions(
        self, page: Page, payload: dict[str, Any], filled: dict[str, str], skipped: list[str]
    ) -> None:
        answer_question = payload["answer_question"]
        choose_option = payload["choose_option"]
        labels = page.locator("label[for^='question_']")
        is_first_dropdown = True

        for i in range(await labels.count()):
            label = labels.nth(i)
            field_id = await label.get_attribute("for")
            question_text = (await label.inner_text()).rstrip("*").strip()
            field = page.locator(f"#{field_id}")

            if await field.count() == 0:
                continue

            if is_consent_question(question_text):
                # Same treatment as an EEO <select> below: never auto-answered,
                # regardless of what kind of field it happens to be on this
                # particular form.
                skipped.append(question_text)
                continue

            tag = await field.evaluate("el => el.tagName.toLowerCase()")
            if tag not in ("input", "textarea"):
                # Never auto-answer a <select> — EEO/demographic self-identification
                # dropdowns live here. MVP.md's non-negotiable is that nothing
                # legally sensitive gets guessed on the candidate's behalf; those
                # are left for the human to fill in during review.
                skipped.append(question_text)
                continue

            if await self._is_combobox(field):
                # These are react-select comboboxes — an <input type="text"> in
                # the DOM, but only a search box over a fixed list, so a
                # free-text answer can never land in them. They are driven by
                # opening the flyout, reading the options the form itself
                # offers, and clicking one of those.
                # Only the first dropdown on the page pays for retries: by the
                # second one, either the first opened (hydration is done, one
                # click is enough) or it never opened after three tries (nothing
                # here is going to open, and retrying each one just burns time).
                choice = await self._select_dropdown_option(
                    page,
                    field_id,
                    question_text,
                    choose_option,
                    attempts=DROPDOWN_OPEN_ATTEMPTS if is_first_dropdown else 1,
                )
                is_first_dropdown = False
                if choice is None:
                    skipped.append(question_text)
                else:
                    filled[question_text] = choice
                continue

            answer = await answer_question(question_text)
            await field.fill(answer)
            filled[question_text] = answer

    async def _is_combobox(self, field: Locator) -> bool:
        """True for a react-select "input that only filters a dropdown" —
        confirmed live on both candidate-location and several custom questions
        on this platform. Shared by core and custom-question filling rather
        than checked twice, since the same trap applies to both.
        """
        return await field.get_attribute("role") == "combobox"

    def _option_selector(self, field_id: str) -> str:
        # react-select scopes every option's id with its own instance id, which
        # here is the input's id — so this never picks up options belonging to
        # another widget that happens to be open (the phone field's ~240-entry
        # country list, for one).
        return f"[id^='react-select-{field_id}-option']"

    async def _wait_until_expanded(self, page: Page, field_id: str, timeout: int) -> bool:
        try:
            await page.wait_for_function(_IS_EXPANDED, arg=field_id, timeout=timeout)
            return True
        except PlaywrightTimeoutError:
            return False

    async def _open_dropdown(self, page: Page, field_id: str, attempts: int) -> bool:
        toggle = page.locator(
            f"#{field_id} >> xpath=ancestor::div[contains(@class,'select__control')]"
            "//button[@aria-label='Toggle flyout']"
        ).first
        if await toggle.count() == 0:
            return False

        for _ in range(attempts):
            await toggle.click()
            if await self._wait_until_expanded(page, field_id, DROPDOWN_OPEN_TIMEOUT_MS):
                return True
        return False

    async def _read_options(self, page: Page, field_id: str) -> list[str]:
        options = page.locator(self._option_selector(field_id))
        return [
            (await options.nth(i).inner_text()).strip() for i in range(await options.count())
        ]

    async def _select_dropdown_option(
        self,
        page: Page,
        field_id: str,
        question_text: str,
        choose_option: Callable[[str, list[str]], Awaitable[str | None]],
        attempts: int,
    ) -> str | None:
        """Open the flyout, offer the real options to the caller, click its pick.

        Returns None — leaving the field for the human — whenever anything is
        uncertain: the flyout won't open, it has no options, or the caller
        declines or names something this form didn't actually offer.
        """
        if not await self._open_dropdown(page, field_id, attempts):
            return None

        options = await self._read_options(page, field_id)
        if not options:
            await page.keyboard.press("Escape")
            return None

        choice = await choose_option(question_text, options)
        if choice not in options:
            await page.keyboard.press("Escape")
            return None

        await page.locator(self._option_selector(field_id)).nth(options.index(choice)).click()
        return choice

    async def _select_location(self, page: Page, field: Locator, value: str) -> str | None:
        """Drive candidate-location's type-to-search: type, wait for the geo
        suggestions, take the first one.

        Falls back to just the leading part of the value ("Raichur" out of
        "Raichur, Karnataka, India") because the suggestion service matches a
        place name, not a pre-formatted full address — found live, a full
        three-part string can return nothing while the city alone matches.
        """
        field_id = await field.get_attribute("id")
        if not field_id:
            return None

        for attempt in dict.fromkeys((value, value.split(",")[0].strip())):
            if not attempt:
                continue
            await field.click()
            await field.fill("")
            await field.press_sequentially(attempt, delay=50)

            # Two stages on purpose: the widget flips aria-expanded as soon as
            # its own JS reacts to the typing, so a page where nothing is live
            # fails here in under a second instead of burning the full lookup
            # budget. Only a widget that proved it is awake gets that budget.
            if not await self._wait_until_expanded(page, field_id, LOCATION_OPEN_TIMEOUT_MS):
                continue
            try:
                await page.locator(self._option_selector(field_id)).first.wait_for(
                    timeout=LOCATION_SEARCH_TIMEOUT_MS
                )
            except PlaywrightTimeoutError:
                continue

            options = await self._read_options(page, field_id)
            if not options:
                continue
            await page.locator(self._option_selector(field_id)).first.click()
            return options[0]

        await field.fill("")
        return None

    async def _has_captcha(self, page: Page) -> bool:
        count = await page.locator(
            "iframe[src*='recaptcha'], iframe[src*='hcaptcha'], #g-recaptcha-response"
        ).count()
        return count > 0
