import time

from sqlalchemy import Row, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.adapters.ashby import AshbyFormAdapter
from app.automation.adapters.greenhouse import GreenhouseFormAdapter
from app.automation.adapters.lever import LeverFormAdapter
from app.automation.base import ATSAdapter
from app.models.application import Application, ApplicationState
from app.models.fill_attempt import FillAttempt, FillAttemptStatus
from app.models.job import Job as JobModel
from app.models.profile import Profile
from app.models.resume_variant import ResumeVariant
from app.services.applications import IllegalStateTransition, apply_transition
from app.services.tailoring.draft_answer import ensure_draft_answer, ensure_draft_option
from app.services.tailoring.resume_pdf import (
    UnrenderableResumeContent,
    base_resume_pdf_filename,
    ensure_resume_pdf,
    render_base_resume_pdf,
    resume_pdf_filename,
)

# One entry today; more ATS platforms get their own adapter and a slot here,
# matched by URL shape via adapter.matches() — see GreenhouseFormAdapter's own
# docstring for why a company's custom-branded careers page (a different DOM
# entirely) doesn't fall under the Greenhouse adapter even when it embeds
# Greenhouse underneath.
ADAPTERS: list[ATSAdapter] = [
    GreenhouseFormAdapter(),
    LeverFormAdapter(),
    AshbyFormAdapter(),
]


class NoAdapterForUrl(ValueError):
    """Raised when no registered adapter recognizes a job's application URL."""


# Every column of a fill attempt except the screenshot, plus a SQL-side answer to
# "is there one". Reading attempts back is a list operation — the detail page
# shows a run's history — and selecting the model would pull every full-page PNG
# out of Postgres to render a few dates and counts.
FILL_ATTEMPT_COLUMNS = (
    FillAttempt.id,
    FillAttempt.application_id,
    FillAttempt.status,
    FillAttempt.filled_fields,
    FillAttempt.skipped_fields,
    FillAttempt.duration_ms,
    FillAttempt.created_at,
    FillAttempt.screenshot.is_not(None).label("has_screenshot"),
)


async def list_fill_attempts(application_id: int, db: AsyncSession) -> list[Row]:
    """Every run against this application's form, newest first."""
    result = await db.execute(
        select(*FILL_ATTEMPT_COLUMNS)
        .where(FillAttempt.application_id == application_id)
        .order_by(FillAttempt.created_at.desc(), FillAttempt.id.desc())
    )
    return list(result.all())


async def get_fill_attempt(attempt_id: int, db: AsyncSession) -> Row | None:
    result = await db.execute(select(*FILL_ATTEMPT_COLUMNS).where(FillAttempt.id == attempt_id))
    return result.one_or_none()


async def get_fill_attempt_screenshot(attempt_id: int, db: AsyncSession) -> bytes | None:
    """Fetched on its own, so the bytes only ever leave the database when
    something is actually going to display them.
    """
    result = await db.execute(
        select(FillAttempt.screenshot).where(FillAttempt.id == attempt_id)
    )
    return result.scalar_one_or_none()


async def _find_adapter(application_url: str) -> ATSAdapter:
    for adapter in ADAPTERS:
        if await adapter.matches(application_url):
            return adapter
    raise NoAdapterForUrl(f"No ATS adapter registered for {application_url}")


async def fill_application_form(
    application: Application, profile: Profile, job: JobModel, db: AsyncSession
) -> FillAttempt:
    """Fill the real application form for review — never submits it.

    The result is persisted as a FillAttempt and returned as one: the review it
    exists to support ("check what I skipped before submitting by hand") sends
    the reviewer off to the live posting, and anything held only in the page
    they leave is gone when they come back.

    If the form turns out to need a CAPTCHA solved, the application is moved
    to pending_captcha (when that's a legal transition from its current state;
    otherwise the attempt is still recorded, just without a state change —
    this function is safe to call from any state, not only ready_for_review).
    Draft answers to any custom question the form asks are generated through
    the same cached, grounded path ensure_draft_answer already provides, so a
    retried fill (e.g. after a human manually solves the captcha) reuses the
    same answers rather than regenerating and risking a different one.
    """
    # Wall-clock from here, not just around adapter.fill(): rendering the resume
    # and generating an answer per question are part of what the caller waits
    # for, and a duration that excluded them would describe nothing real.
    started = time.perf_counter()
    adapter = await _find_adapter(job.url)

    resume_variant = None
    if application.resume_variant_id is not None:
        resume_variant = (
            await db.execute(
                select(ResumeVariant).where(ResumeVariant.id == application.resume_variant_id)
            )
        ).scalar_one_or_none()

    if resume_variant is not None:
        resume_bytes = await ensure_resume_pdf(profile, resume_variant, db)
        resume_filename = resume_pdf_filename(profile, resume_variant)
    else:
        # No workflow sets Application.resume_variant_id today, so this is the
        # common case, not a fallback for an edge case — without it, the resume
        # field would be silently skipped on every application, always.
        #
        # Unlike a ResumeVariant's LLM-generated content (tuned to the fold map
        # in resume_pdf.py), profile.full_resume_text is arbitrary user-typed
        # text and can contain a character outside the built-in PDF fonts —
        # found live, a stray "↗" crashed this. Losing the whole fill (every
        # core field and every custom-question answer) over one unrenderable
        # resume is a bad trade; skip just the resume, same honest-skip pattern
        # already used for a combobox or a consent question.
        try:
            resume_bytes = render_base_resume_pdf(profile)
            resume_filename = base_resume_pdf_filename(profile)
        except UnrenderableResumeContent:
            resume_bytes = None
            resume_filename = "resume.pdf"

    first_name, _, last_name = profile.name.partition(" ")

    async def answer_question(question_text: str) -> str:
        draft = await ensure_draft_answer(application, profile, job, question_text, db)
        return draft.answer_text

    async def choose_option(question_text: str, options: list[str]) -> str | None:
        return await ensure_draft_option(application, profile, job, question_text, options, db)

    payload = {
        "first_name": first_name,
        "last_name": last_name,
        "email": profile.email,
        "phone": profile.phone,
        "location": profile.location,
        # Lever asks for these outright; Greenhouse leaves them to a custom
        # question, where they reach the form through answer_question instead.
        "linkedin_url": profile.linkedin_url,
        "portfolio_url": profile.portfolio_url,
        "resume_bytes": resume_bytes,
        "resume_filename": resume_filename,
        "answer_question": answer_question,
        "choose_option": choose_option,
    }

    result = await adapter.fill(job.url, payload)

    attempt = FillAttempt(
        application_id=application.id,
        status=FillAttemptStatus(result["status"]),
        filled_fields=result["filled_fields"],
        skipped_fields=result["skipped_fields"],
        screenshot=result["screenshot"],
        duration_ms=int((time.perf_counter() - started) * 1000),
    )
    db.add(attempt)
    # Committed before the transition below rather than with it: a state change
    # that turns out to be illegal must not take the record of the run with it.
    await db.commit()
    await db.refresh(attempt)

    if result["status"] == "captcha_required":
        try:
            await apply_transition(application, ApplicationState.PENDING_CAPTCHA, db)
        except IllegalStateTransition:
            pass

    return attempt
