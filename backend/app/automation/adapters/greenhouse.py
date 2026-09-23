import time
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import parse_qs, urlparse

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Locator, Page, async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.automation.base import (
    ATSAdapter,
    FillResult,
    FillStatus,
    FormContext,
    clear_text_field,
    confirm_file_fill,
    fill_text_answer,
    has_captcha,
    is_consent_question,
)

# Greenhouse serves embedded forms from this path, whatever site is framing it.
EMBED_FRAME_MARKER = "greenhouse.io/embed"

# How long to wait for the core name/email fields to appear before giving up —
# either they're already there, or an "Apply" click needs to reveal them.
REVEAL_TIMEOUT_MS = 8000
# Longer after clicking Apply: that can be a full navigation to another page
# which then has to load an embedded form in an iframe of its own.
APPLY_REVEAL_TIMEOUT_MS = 20000
FORM_POLL_INTERVAL_MS = 400

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
# Long enough for a late hydration pass to clobber a re-fill if it is going
# to — measured at roughly two seconds on a real embedded form.
REFILL_SETTLE_MS = 2500
LOCATION_SEARCH_TIMEOUT_MS = 5000

_IS_EXPANDED = "id => document.getElementById(id)?.getAttribute('aria-expanded') === 'true'"

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
        """Greenhouse-hosted postings, and branded careers sites that embed one.

        A company running its own careers page still hands the application off
        to Greenhouse in an iframe, and links to it with Greenhouse's own
        gh_jid parameter — the same form, the same field ids, just framed. That
        parameter is the reliable signal; the host name is not, since it is
        whatever company owns the site.
        """
        parsed = urlparse(application_url)
        if parsed.hostname and parsed.hostname.endswith("greenhouse.io"):
            return True
        return "gh_jid" in parse_qs(parsed.query)

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
        form = await self._reveal_form(page)
        if form is None:
            return FillResult(status="form_not_found", filled_fields={}, skipped_fields=[], screenshot=None)

        filled: dict[str, str] = {}
        skipped: list[str] = []
        # Every plain text value written, kept so it can be read back at the end
        # — see _confirm_text_fills for why believing .fill() is not enough.
        text_fills: list[tuple[str, Locator, str]] = []
        file_fills: list[tuple[str, Locator, dict]] = []

        await self._fill_core_fields(form, page, payload, filled, skipped, text_fills, file_fills)
        await self._fill_custom_questions(form, page, payload, filled, skipped, text_fills)
        await self._confirm_text_fills(page, text_fills, filled, skipped)
        await confirm_file_fill(page, form, file_fills, filled, skipped, REFILL_SETTLE_MS)

        # Checked after filling, not before: a fully-filled form is what makes
        # the pending_captcha review screen useful — the human should see every
        # answer already in place and only need to solve the one checkbox.
        status: FillStatus = "captcha_required" if await has_captcha(page, form) else "filled"
        # Always the page, never the frame: the human reviewing this needs to
        # see the posting as it really looks, framing and all.
        screenshot = await page.screenshot(full_page=True)

        return FillResult(status=status, filled_fields=filled, skipped_fields=skipped, screenshot=screenshot)

    async def _reveal_form(self, page: Page) -> FormContext | None:
        form = await self._poll_for_form(page, REVEAL_TIMEOUT_MS)
        if form is not None:
            return form

        # A branded careers page usually shows the posting first and only loads
        # the application behind an Apply link, which can be a real navigation.
        apply = page.locator("a:has-text('Apply'), button:has-text('Apply')").first
        if await apply.count() == 0:
            return None
        await apply.click()
        return await self._poll_for_form(page, APPLY_REVEAL_TIMEOUT_MS)

    async def _poll_for_form(self, page: Page, timeout_ms: int) -> FormContext | None:
        """Watch the page and its frames until the form turns up in one of them.

        Polled rather than waited on: the form may arrive either in the page
        itself or in an embed frame that does not exist yet, and there is no
        single locator that covers both.
        """
        deadline = time.monotonic() + timeout_ms / 1000
        while True:
            if await self._has_first_name(page):
                return page
            for frame in page.frames:
                if EMBED_FRAME_MARKER in frame.url and await self._has_first_name(frame):
                    return frame
            if time.monotonic() >= deadline:
                return None
            await page.wait_for_timeout(FORM_POLL_INTERVAL_MS)

    async def _confirm_text_fills(
        self,
        page: Page,
        text_fills: list[tuple[str, Locator, str]],
        filled: dict[str, str],
        skipped: list[str],
    ) -> None:
        """Read every written value back, re-write the ones that did not stick,
        and demote whatever still will not hold.

        Found live on an embedded form: the frame paints its fields before React
        finishes hydrating, and hydration then resets anything written in that
        window — measured at about two seconds, with first_name, last_name and
        email silently emptied while the later fields survived. .fill() had
        reported success for all of them, so the result claimed six filled
        fields over a form showing three.

        A fixed wait before filling would just be a guess at someone else's
        hydration time. Reading the value back is the thing that is actually
        true, and by the time this runs the slow work (a geo lookup, an LLM call
        per question) has already given the page all the settling time it needs.
        """
        for key, locator, value in text_fills:
            if await self._value_holds(locator, value):
                continue

            await locator.fill(value)
            await page.wait_for_timeout(REFILL_SETTLE_MS)
            if await self._value_holds(locator, value):
                continue

            # Never leave a claim standing that the form disagrees with — nor
            # the form holding a fragment of one. See clear_text_field.
            await clear_text_field(locator)
            filled.pop(key, None)
            skipped.append(key)

    async def _value_holds(self, locator: Locator, value: str) -> bool:
        try:
            return await locator.input_value() == value
        except PlaywrightError:
            return False

    async def _has_first_name(self, form: FormContext) -> bool:
        try:
            return await form.locator(CORE_FIELD_SELECTORS["first_name"]).count() > 0
        except PlaywrightError:
            # A frame can be torn down mid-poll by the page navigating; that is
            # simply "not the form", not a failure worth aborting the fill for.
            return False

    async def _fill_core_fields(
        self,
        form: FormContext,
        page: Page,
        payload: dict[str, Any],
        filled: dict[str, str],
        skipped: list[str],
        text_fills: list[tuple[str, Locator, str]],
        file_fills: list[tuple[str, Locator, dict]],
    ) -> None:
        for field, selector in CORE_FIELD_SELECTORS.items():
            value = payload.get(field)
            locator = form.locator(selector)
            if not value or await locator.count() == 0:
                skipped.append(selector)
                continue
            if await self._is_combobox(locator):
                # candidate-location is a react-select combobox on this platform,
                # not a plain text field — .fill() alone writes text the widget
                # never treats as a real selection, so it has to be driven as a
                # search-and-pick instead.
                selected = await self._select_location(form, locator, str(value))
                if selected is None:
                    skipped.append(selector)
                else:
                    filled[selector] = selected
                continue
            await locator.fill(str(value))
            filled[selector] = str(value)
            text_fills.append((selector, locator, str(value)))

        resume_bytes = payload.get("resume_bytes")
        resume_field = form.locator("#resume")
        if resume_bytes and await resume_field.count() > 0:
            resume_file = {
                "name": payload.get("resume_filename") or "resume.pdf",
                "mimeType": "application/pdf",
                "buffer": resume_bytes,
            }
            await resume_field.set_input_files(resume_file)
            filled["#resume"] = resume_file["name"]
            # Read back with everything else — a late re-render empties a file
            # input exactly as it empties a text one. See confirm_file_fill.
            file_fills.append(("#resume", resume_field, resume_file))
        else:
            skipped.append("#resume")

    async def _fill_custom_questions(
        self,
        form: FormContext,
        page: Page,
        payload: dict[str, Any],
        filled: dict[str, str],
        skipped: list[str],
        text_fills: list[tuple[str, Locator, str]],
    ) -> None:
        answer_question = payload["answer_question"]
        choose_option = payload["choose_option"]
        labels = form.locator("label[for^='question_']")
        is_first_dropdown = True

        for i in range(await labels.count()):
            label = labels.nth(i)
            field_id = await label.get_attribute("for")
            question_text = (await label.inner_text()).rstrip("*").strip()
            field = form.locator(f"#{field_id}")

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
                    form,
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

            await fill_text_answer(
                field, question_text, answer_question, filled, skipped, text_fills
            )

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

    async def _wait_until_expanded(self, form: FormContext, field_id: str, timeout: int) -> bool:
        try:
            await form.wait_for_function(_IS_EXPANDED, arg=field_id, timeout=timeout)
            return True
        except PlaywrightTimeoutError:
            return False

    async def _open_dropdown(self, form: FormContext, field_id: str, attempts: int) -> bool:
        toggle = form.locator(
            f"#{field_id} >> xpath=ancestor::div[contains(@class,'select__control')]"
            "//button[@aria-label='Toggle flyout']"
        ).first
        if await toggle.count() == 0:
            return False

        for _ in range(attempts):
            await toggle.click()
            if await self._wait_until_expanded(form, field_id, DROPDOWN_OPEN_TIMEOUT_MS):
                return True
        return False

    async def _read_options(self, form: FormContext, field_id: str) -> list[str]:
        options = form.locator(self._option_selector(field_id))
        return [
            (await options.nth(i).inner_text()).strip() for i in range(await options.count())
        ]

    async def _select_dropdown_option(
        self,
        form: FormContext,
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
        if not await self._open_dropdown(form, field_id, attempts):
            return None

        options = await self._read_options(form, field_id)
        if not options:
            await page.keyboard.press("Escape")
            return None

        choice = await choose_option(question_text, options)
        if choice not in options:
            await page.keyboard.press("Escape")
            return None

        await form.locator(self._option_selector(field_id)).nth(options.index(choice)).click()
        return choice

    async def _select_location(self, form: FormContext, field: Locator, value: str) -> str | None:
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
            if not await self._wait_until_expanded(form, field_id, LOCATION_OPEN_TIMEOUT_MS):
                continue
            try:
                await form.locator(self._option_selector(field_id)).first.wait_for(
                    timeout=LOCATION_SEARCH_TIMEOUT_MS
                )
            except PlaywrightTimeoutError:
                continue

            options = await self._read_options(form, field_id)
            if not options:
                continue
            await form.locator(self._option_selector(field_id)).first.click()
            return options[0]

        await field.fill("")
        return None

