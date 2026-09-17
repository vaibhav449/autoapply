from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application, ApplicationState
from app.models.job import Job as JobModel
from app.models.profile import Profile

ALLOWED_TRANSITIONS: dict[ApplicationState, set[ApplicationState]] = {
    ApplicationState.INTERESTED: {ApplicationState.TAILORING, ApplicationState.REJECTED_BY_USER},
    ApplicationState.TAILORING: {
        ApplicationState.READY_FOR_REVIEW,
        ApplicationState.REJECTED_BY_USER,
    },
    ApplicationState.READY_FOR_REVIEW: {
        ApplicationState.APPROVED,
        ApplicationState.PENDING_CAPTCHA,
        ApplicationState.REJECTED_BY_USER,
    },
    ApplicationState.PENDING_CAPTCHA: {
        ApplicationState.SUBMITTED,
        ApplicationState.REJECTED_BY_USER,
    },
    ApplicationState.APPROVED: {ApplicationState.SUBMITTED, ApplicationState.REJECTED_BY_USER},
    ApplicationState.SUBMITTED: {ApplicationState.RESPONSE_TRACKED},
    ApplicationState.RESPONSE_TRACKED: set(),
    ApplicationState.REJECTED_BY_USER: set(),
}


class IllegalStateTransition(ValueError):
    """Raised when a requested transition isn't a legal edge in the state machine."""


def validate_transition(current: ApplicationState, target: ApplicationState) -> None:
    """Pure — no DB, no side effects. Exactly the kind of deterministic logic
    MVP.md calls out for fast unit coverage, same spirit as the scoring math.
    """
    if target not in ALLOWED_TRANSITIONS[current]:
        raise IllegalStateTransition(f"Cannot move from {current.value!r} to {target.value!r}.")


async def apply_transition(
    application: Application, target: ApplicationState, db: AsyncSession
) -> None:
    validate_transition(application.state, target)
    application.state = target
    if target == ApplicationState.SUBMITTED:
        application.submitted_at = datetime.now(UTC)
    await db.commit()


async def get_or_create_application(
    profile: Profile, job: JobModel, db: AsyncSession
) -> Application:
    """Idempotent — clicking "apply" twice on the same job should return the
    existing in-progress application, not error, unlike ResumeVariant's
    duplicate-role_label 409 (a genuinely different intent there).
    """
    result = await db.execute(
        select(Application).where(
            Application.profile_id == profile.id, Application.job_id == job.id
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    application = Application(profile_id=profile.id, job_id=job.id)
    db.add(application)
    await db.commit()
    return application
