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
    has_captcha,
    is_consent_question,
)

FORM_TIMEOUT_MS = 15000
REFILL_SETTLE_MS = 1500

# Lever keys its fields by name rather than id, and uses one "name" field where
# Greenhouse has first_name/last_name. Values come from the payload under these
# keys; "name" is assembled from the two the payload carries.
CORE_FIELD_SELECTORS = {
    "email": 'input[name="email"]',
    "phone": 'input[name="phone"]',
    "location": 'input[name="location"]',
    "linkedin_url": 'input[name="urls[LinkedIn]"]',
    "portfolio_url": 'input[name="urls[GitHub]"]',
}

# Every custom question Lever renders is a cards[<uuid>][fieldN] control...
QUESTION_SELECTOR = '[name^="cards["]'
# ...except baseTemplate, which carries the template's id rather than an answer
# and shares its question's label, so it would otherwise look like a duplicate.
TEMPLATE_FIELD_MARKER = "[baseTemplate]"
# Self-identification lives in its own namespace here, which makes it cleanly
# separable — unlike Greenhouse, where EEO and real questions share a shape and
# every <select> had to be refused to be safe.
EEO_FIELD_SELECTOR = '[name^="eeo["]'

# Lever's own placeholder option, which is not an answer.
PLACEHOLDER_OPTIONS = {"select...", "select ...", ""}


class LeverFormAdapter(ATSAdapter):
    """Fills a Lever-hosted application form.

    Never clicks submit — same non-negotiable as every other adapter.

    Two things are genuinely easier here than on Greenhouse. The questions are
    real <select> and <textarea> elements rather than react-select widgets, so
    no flyout has to be opened to read the options. And self-identification is
    namespaced under eeo[...], so a question dropdown can be answered without
    any risk of touching a demographic one — on Greenhouse the two are
    indistinguishable by shape, which is why every <select> there is refused.
    """

    async def matches(self, application_url: str) -> bool:
        host = urlparse(application_url).hostname or ""
        return host == "lever.co" or host.endswith(".lever.co")

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
        await self._fill_custom_questions(page, payload, filled, skipped, text_fills)
        await self._confirm_text_fills(page, text_fills, filled, skipped)
        await confirm_file_fill(page, page, file_fills, filled, skipped, REFILL_SETTLE_MS)

        status: FillStatus = "captcha_required" if await has_captcha(page) else "filled"
        screenshot = await page.screenshot(full_page=True)
        return FillResult(
            status=status, filled_fields=filled, skipped_fields=skipped, screenshot=screenshot
        )

    async def _reveal_form(self, page: Page) -> bool:
        """A Lever posting shows the description first and puts the form behind
        an apply link, on a /apply URL of its own.
        """
        if await self._has_form(page):
            return True

        apply = page.locator("a:has-text('Apply'), button:has-text('Apply')").first
        if await apply.count() == 0:
            return False
        await apply.click()
        try:
            await page.locator('input[name="email"]').wait_for(timeout=FORM_TIMEOUT_MS)
        except PlaywrightTimeoutError:
            return False
        return True

    async def _has_form(self, page: Page) -> bool:
        return await page.locator('input[name="email"]').count() > 0

    async def _fill_core_fields(
        self,
        page: Page,
        payload: dict[str, Any],
        filled: dict[str, str],
        skipped: list[str],
        text_fills: list[tuple[str, Locator, str]],
        file_fills: list[tuple[str, Locator, dict]],
    ) -> None:
        # One field for the whole name, unlike Greenhouse's split pair.
        full_name = " ".join(
            part for part in (payload.get("first_name"), payload.get("last_name")) if part
        )
        for key, selector, value in [
            ("name", 'input[name="name"]', full_name),
            *(
                (key, selector, payload.get(key))
                for key, selector in CORE_FIELD_SELECTORS.items()
            ),
        ]:
            locator = page.locator(selector)
            if not value or await locator.count() == 0:
                skipped.append(selector)
                continue
            await locator.fill(str(value))
            filled[selector] = str(value)
            text_fills.append((selector, locator, str(value)))

        resume_bytes = payload.get("resume_bytes")
        resume_field = page.locator('input[type="file"][name="resume"]')
        if resume_bytes and await resume_field.count() > 0:
            resume_file = {
                "name": payload.get("resume_filename") or "resume.pdf",
                "mimeType": "application/pdf",
                "buffer": resume_bytes,
            }
            await resume_field.set_input_files(resume_file)
            filled["resume"] = resume_file["name"]
            # Read back with everything else — see confirm_file_fill.
            file_fills.append(("resume", resume_field, resume_file))
        else:
            skipped.append("resume")

    async def _fill_custom_questions(
        self,
        page: Page,
        payload: dict[str, Any],
        filled: dict[str, str],
        skipped: list[str],
        text_fills: list[tuple[str, Locator, str]],
    ) -> None:
        answer_question = payload["answer_question"]
        choose_option = payload["choose_option"]

        fields = page.locator(QUESTION_SELECTOR)
        for i in range(await fields.count()):
            field = fields.nth(i)
            name = await field.get_attribute("name") or ""
            if TEMPLATE_FIELD_MARKER in name:
                continue

            question_text = await self._question_text(field)
            if not question_text:
                skipped.append(name)
                continue

            if is_consent_question(question_text):
                skipped.append(question_text)
                continue

            tag = await field.evaluate("el => el.tagName.toLowerCase()")
            if tag == "select":
                choice = await self._select_option(field, question_text, choose_option)
                if choice is None:
                    skipped.append(question_text)
                else:
                    filled[question_text] = choice
                continue

            answer = await answer_question(question_text)
            await field.fill(answer)
            filled[question_text] = answer
            text_fills.append((question_text, field, answer))

    async def _question_text(self, field: Locator) -> str | None:
        """Lever renders the question above its control rather than in a label
        tied to it by id, so it is found by walking up to the nearest container
        that carries text.
        """
        text = await field.evaluate(
            """el => {
                let node = el;
                for (let i = 0; i < 6 && node.parentElement; i++) {
                    node = node.parentElement;
                    const hit = node.querySelector('.application-label, .text, label');
                    if (hit && (hit.innerText || '').trim()) return hit.innerText.trim();
                }
                return null;
            }"""
        )
        if not text:
            return None
        # Lever marks required questions with a trailing asterisk on its own line.
        return text.replace("✱", "").strip()

    async def _select_option(self, field: Locator, question_text: str, choose_option) -> str | None:
        """Answer a native <select> from its own options.

        Same gate as everywhere else: the caller's pick is checked against what
        this form actually offers, so a value the form never listed cannot be
        selected — the worst case is an honest skip.
        """
        options = [
            text.strip()
            for text in await field.locator("option").all_inner_texts()
            if text.strip().lower() not in PLACEHOLDER_OPTIONS
        ]
        if not options:
            return None

        choice = await choose_option(question_text, options)
        if choice not in options:
            return None

        await field.select_option(label=choice)
        return choice

    async def _confirm_text_fills(
        self,
        page: Page,
        text_fills: list[tuple[str, Locator, str]],
        filled: dict[str, str],
        skipped: list[str],
    ) -> None:
        """Read every written value back and demote whatever did not hold.

        Same reasoning as the Greenhouse adapter: a form that re-renders after
        a write leaves .fill() reporting success over an empty field, and a
        result that claims a value the form does not have is worse than one
        that admits it skipped something.
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
