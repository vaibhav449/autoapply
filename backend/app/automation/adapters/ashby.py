from typing import Any
from urllib.parse import urlparse

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Locator, Page, async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.automation.base import (
    ATSAdapter,
    FillResult,
    FillStatus,
    clear_text_field,
    confirm_file_fill,
    fill_text_answer,
    has_captcha,
    is_consent_question,
)

FORM_TIMEOUT_MS = 20000
# Long enough for a client-rendered posting to paint its Apply button, short
# enough that a dead URL fails quickly rather than hanging the whole fill.
REVEAL_TIMEOUT_MS = 12000
REFILL_SETTLE_MS = 1500

# Ashby gives its own fields stable ids and everything else a per-job UUID, so
# these five are the only selectors that survive from posting to posting.
NAME_SELECTOR = "#_systemfield_name"
EMAIL_SELECTOR = "#_systemfield_email"
RESUME_SELECTOR = "#_systemfield_resume"
# Phone carries a UUID like any custom field; its input type is what identifies it.
PHONE_SELECTOR = 'input[type="tel"]'

# Each question is wrapped in one of these. Matched on the substring because the
# full class carries a build hash (_fieldEntry_1e3gg_28) that changes per deploy.
FIELD_ENTRY_SELECTOR = '[class*="fieldEntry"]'

# Ashby's own marketing opt-in. It lives inside the Phone Number entry, so the
# question text above it reads "Phone Number" and says nothing about consent —
# the radio labels do, but only if you look at them. Named explicitly rather
# than relying on the wording, since agreeing to be texted is the candidate's
# decision either way.
CONSENT_FIELD_NAMES = {"communicationConsent"}

BOOLEAN_OPTIONS = ["Yes", "No"]


class AshbyFormAdapter(ATSAdapter):
    """Fills an Ashby-hosted application form.

    Never clicks submit, like every other adapter.

    Ashby needs two control types the others did not. Questions appear as radio
    groups (the options are separate <input type=radio> sharing a name, each
    labelled by a label[for=...]) and as single checkboxes standing in for a
    yes/no answer. Both are constrained choices, so both go through the same
    gate as a dropdown: the caller picks from the options this form actually
    renders, and anything else is refused.
    """

    async def matches(self, application_url: str) -> bool:
        host = urlparse(application_url).hostname or ""
        return host == "ashbyhq.com" or host.endswith(".ashbyhq.com")

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
            return FillResult(
                status="form_not_found", filled_fields={}, skipped_fields=[], screenshot=None
            )

        filled: dict[str, str] = {}
        skipped: list[str] = []
        text_fills: list[tuple[str, Locator, str]] = []
        file_fills: list[tuple[str, Locator, dict]] = []

        await self._fill_core_fields(page, payload, filled, skipped, text_fills, file_fills)
        await self._fill_questions(page, payload, filled, skipped, text_fills)
        await self._confirm_text_fills(page, text_fills, filled, skipped)
        await confirm_file_fill(page, page, file_fills, filled, skipped, REFILL_SETTLE_MS)

        status: FillStatus = "captcha_required" if await has_captcha(page) else "filled"
        screenshot = await page.screenshot(full_page=True)
        return FillResult(
            status=status, filled_fields=filled, skipped_fields=skipped, screenshot=screenshot
        )

    async def _reveal_form(self, page: Page) -> bool:
        """The form is a client-rendered route behind an Apply button. Going
        straight to /application renders an empty shell, so the button is the
        only way in.

        Everything here is waited for rather than counted. Ashby paints nothing
        at domcontentloaded, so asking whether the Apply button exists the
        instant the page arrives always answers no — found live, where a form
        that fills perfectly against a captured snapshot reported
        form_not_found against the posting it was captured from.
        """
        form = page.locator(NAME_SELECTOR)
        apply = (
            page.get_by_role("button", name="apply", exact=False)
            .or_(page.get_by_role("link", name="apply", exact=False))
            .first
        )

        # Whichever arrives first: an already-open form, or the way into one.
        if not await self._appears(form.or_(apply).first, REVEAL_TIMEOUT_MS):
            return False
        if await form.count() > 0:
            return True

        await apply.click()
        return await self._appears(form, FORM_TIMEOUT_MS)

    async def _appears(self, locator: Locator, timeout_ms: int) -> bool:
        try:
            await locator.wait_for(timeout=timeout_ms)
        except PlaywrightTimeoutError:
            return False
        return True

    async def _fill_core_fields(
        self,
        page: Page,
        payload: dict[str, Any],
        filled: dict[str, str],
        skipped: list[str],
        text_fills: list[tuple[str, Locator, str]],
        file_fills: list[tuple[str, Locator, dict]],
    ) -> None:
        full_name = " ".join(
            part for part in (payload.get("first_name"), payload.get("last_name")) if part
        )
        for selector, value in (
            (NAME_SELECTOR, full_name),
            (EMAIL_SELECTOR, payload.get("email")),
            (PHONE_SELECTOR, payload.get("phone")),
        ):
            locator = page.locator(selector).first
            if not value or await locator.count() == 0:
                skipped.append(selector)
                continue
            await locator.fill(str(value))
            filled[selector] = str(value)
            text_fills.append((selector, locator, str(value)))

        resume_bytes = payload.get("resume_bytes")
        resume_field = page.locator(RESUME_SELECTOR)
        if resume_bytes and await resume_field.count() > 0:
            resume_file = {
                "name": payload.get("resume_filename") or "resume.pdf",
                "mimeType": "application/pdf",
                "buffer": resume_bytes,
            }
            await resume_field.set_input_files(resume_file)
            filled[RESUME_SELECTOR] = resume_file["name"]
            # Read back with everything else — see confirm_file_fill.
            file_fills.append((RESUME_SELECTOR, resume_field, resume_file))
        else:
            skipped.append(RESUME_SELECTOR)

    async def _fill_questions(
        self,
        page: Page,
        payload: dict[str, Any],
        filled: dict[str, str],
        skipped: list[str],
        text_fills: list[tuple[str, Locator, str]],
    ) -> None:
        answer_question = payload["answer_question"]
        choose_option = payload["choose_option"]

        entries = page.locator(FIELD_ENTRY_SELECTOR)
        for i in range(await entries.count()):
            entry = entries.nth(i)
            question_text = await self._question_text(entry)
            if not question_text:
                continue
            if await self._is_core_entry(entry):
                continue
            if is_consent_question(question_text) or await self._is_consent_entry(entry):
                skipped.append(question_text)
                continue

            radios = entry.locator('input[type="radio"]')
            checkboxes = entry.locator('input[type="checkbox"]')
            texts = entry.locator('input[type="text"], textarea')

            if await radios.count() > 0:
                choice = await self._choose_radio(entry, radios, question_text, choose_option)
            elif await checkboxes.count() > 0:
                choice = await self._choose_checkbox(checkboxes.first, question_text, choose_option)
            elif await texts.count() > 0:
                await fill_text_answer(
                    texts.first, question_text, answer_question, filled, skipped, text_fills
                )
                continue
            else:
                # A file question (a cover-letter upload, say). Nothing is
                # generated for these, so it is left for the human rather than
                # reported as handled.
                skipped.append(question_text)
                continue

            if choice is None:
                skipped.append(question_text)
            else:
                filled[question_text] = choice

    async def _question_text(self, entry: Locator) -> str | None:
        text = await entry.evaluate(
            """el => {
                const hit = el.querySelector('label, legend');
                return hit ? (hit.innerText || '').trim() : null;
            }"""
        )
        if not text:
            return None
        return text.replace("✱", "").replace("*", "").strip() or None

    async def _is_core_entry(self, entry: Locator) -> bool:
        """Core fields live in field entries too, and are already handled."""
        return await entry.evaluate(
            """el => Boolean(
                el.querySelector('[id^="_systemfield_"]') ||
                el.querySelector('input[type="tel"]')
            )"""
        )

    async def _is_consent_entry(self, entry: Locator) -> bool:
        return await entry.evaluate(
            """(el, names) => [...el.querySelectorAll('[name]')]
                 .some(c => names.includes(c.getAttribute('name')))""",
            list(CONSENT_FIELD_NAMES),
        )

    async def _choose_radio(
        self, entry: Locator, radios: Locator, question_text: str, choose_option
    ) -> str | None:
        """Each radio is labelled by a label[for=<its id>], which is where the
        option text lives — the group's own label is the question.
        """
        labels = await entry.evaluate(
            """el => [...el.querySelectorAll('input[type="radio"]')].map(r => {
                const lab = r.id ? el.querySelector(`label[for="${r.id}"]`) : null;
                return lab ? (lab.innerText || '').trim() : null;
            })"""
        )
        options = [label for label in labels if label]
        if not options:
            return None

        choice = await choose_option(question_text, options)
        if choice not in options:
            return None

        await radios.nth(labels.index(choice)).check()
        return choice

    async def _choose_checkbox(
        self, checkbox: Locator, question_text: str, choose_option
    ) -> str | None:
        """A lone checkbox is a yes/no question wearing a different control.

        Offered as Yes/No so the caller answers the question rather than being
        asked whether to tick a box, and only a "Yes" actually ticks it —
        leaving it clear is already what "No" looks like on the submitted form.
        """
        choice = await choose_option(question_text, list(BOOLEAN_OPTIONS))
        if choice not in BOOLEAN_OPTIONS:
            return None

        if choice == "Yes":
            await checkbox.check()
        return choice

    async def _confirm_text_fills(
        self,
        page: Page,
        text_fills: list[tuple[str, Locator, str]],
        filled: dict[str, str],
        skipped: list[str],
    ) -> None:
        """Read back what was written, same as the other adapters: a form that
        re-renders after a write leaves .fill() reporting success over an empty
        field, and claiming a value the form does not have is the one failure
        worth going out of the way to prevent.
        """
        for key, locator, value in text_fills:
            if await self._value_holds(locator, value):
                continue

            await locator.fill(value)
            await page.wait_for_timeout(REFILL_SETTLE_MS)
            if await self._value_holds(locator, value):
                continue

            # Nothing half-written is left behind under a "skipped" label —
            # see clear_text_field.
            await clear_text_field(locator)
            filled.pop(key, None)
            skipped.append(key)

    async def _value_holds(self, locator: Locator, value: str) -> bool:
        try:
            return await locator.input_value() == value
        except PlaywrightError:
            return False
