from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import ALLOWED_TRANSITIONS, Application, ApplicationState
from app.models.application_outcome import ApplicationOutcome, OutcomeKind
from app.models.job import Job as JobModel
from app.models.profile import Profile


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


async def record_outcome(
    application: Application,
    kind: OutcomeKind,
    note: str | None,
    occurred_at: datetime | None,
    db: AsyncSession,
) -> ApplicationOutcome:
    """Log what came back, and move the application along if that is legal.

    The log is the record; the state change is a convenience so the board stops
    showing something as merely submitted once it is demonstrably not. An
    application already past submitted keeps its state — hearing back twice is
    normal (an interview, then an offer) and only the first one has anywhere to
    move to.
    """
    outcome = ApplicationOutcome(
        application_id=application.id,
        kind=kind,
        note=note,
        occurred_at=occurred_at or datetime.now(UTC),
    )
    db.add(outcome)
    await db.commit()

    try:
        await apply_transition(application, ApplicationState.RESPONSE_TRACKED, db)
    except IllegalStateTransition:
        pass

    return outcome


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
