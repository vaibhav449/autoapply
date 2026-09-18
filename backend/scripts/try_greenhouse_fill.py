"""Manually try the Greenhouse form-filling adapter against a real, live
posting — fills the real application form for a real profile, screenshots the
result, and stops. Never clicks Submit; nothing reaches the employer.

Usage:
    python scripts/try_greenhouse_fill.py <profile_id> <job_id>

Find real ids first:
    GET /api/v1/profiles/          — pick a profile id
    GET /api/v1/jobs/               — pick a job whose "url" contains
                                       "greenhouse.io" and whose "closed_at"
                                       is null (still open)

What it does:
    1. Loads the real Profile and Job rows.
    2. Gets or creates the Application for that pair (idempotent — running
       this twice reuses the same row).
    3. Drives it to ready_for_review if it's still fresh, so a detected
       CAPTCHA has somewhere legal to transition to (pending_captcha).
    4. Opens the real posting in a real browser, fills every field it can,
       screenshots the result, and reports what got filled vs. skipped and
       why (see GreenhouseFormAdapter's docstring for the two skip reasons:
       EEO-style <select> dropdowns, and react-select comboboxes that look
       like text inputs but aren't).

The screenshot is saved next to this script as greenhouse-fill-result.png —
open it to see exactly what the real form looks like, filled but untouched
at the Submit button.
"""

import asyncio
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models import cover_letter, resume_variant  # noqa: F401  (register FK targets)
from app.models.application import ApplicationState
from app.models.job import Job as JobModel
from app.models.profile import Profile
from app.services.applications import apply_transition, get_or_create_application
from app.services.automation import NoAdapterForUrl, fill_application_form

OUT = Path(__file__).parent / "greenhouse-fill-result.png"


async def main(profile_id: int, job_id: int) -> None:
    engine = create_async_engine(settings.database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        profile = (
            await db.execute(
                select(Profile).options(selectinload(Profile.projects)).where(Profile.id == profile_id)
            )
        ).scalar_one_or_none()
        if profile is None:
            print(f"No profile with id {profile_id}.")
            return

        job = (await db.execute(select(JobModel).where(JobModel.id == job_id))).scalar_one_or_none()
        if job is None:
            print(f"No job with id {job_id}.")
            return

        print(f"profile: {profile.name} <{profile.email}>")
        print(f"job: {job.title} @ {job.company}  ({job.url})")

        application = await get_or_create_application(profile, job, db)
        print(f"application id={application.id}  state={application.state.value}")

        if application.state == ApplicationState.INTERESTED:
            await apply_transition(application, ApplicationState.TAILORING, db)
            await apply_transition(application, ApplicationState.READY_FOR_REVIEW, db)
            print(f"moved to: {application.state.value}")

        try:
            result = await fill_application_form(application, profile, job, db)
        except NoAdapterForUrl as exc:
            print(f"\n{exc}")
            print("Only Greenhouse-hosted postings (job-boards.greenhouse.io) are supported so far.")
            return

        print("\n--- result ---")
        print("status:", result["status"])
        print(f"\nfilled ({len(result['filled_fields'])}):")
        for field, value in result["filled_fields"].items():
            preview = value[:70] + "…" if len(value) > 70 else value
            print(f"  {field}: {preview}")
        print(f"\nskipped ({len(result['skipped_fields'])}):")
        for field in result["skipped_fields"]:
            print(f"  {field}")

        if result["screenshot"]:
            OUT.write_bytes(result["screenshot"])
            print(f"\nscreenshot: {OUT}")

        await db.refresh(application)
        print(f"\napplication state now: {application.state.value}")

    await engine.dispose()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    asyncio.run(main(int(sys.argv[1]), int(sys.argv[2])))
