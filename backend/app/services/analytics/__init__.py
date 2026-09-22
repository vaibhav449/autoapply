from sqlalchemy import case, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.application_outcome import ApplicationOutcome, OutcomeKind
from app.models.resume_variant import ResumeVariant
from app.schemas.analytics import AnalyticsSummary, VariantPerformance

# A recorded "no response" is a decision with a date on it, not a reply — it
# belongs in the outcome breakdown but must never count toward the response rate.
RESPONDED = ApplicationOutcome.kind != OutcomeKind.NO_RESPONSE


async def _count_applications_with(db: AsyncSession, condition) -> int:
    """Distinct applications, because one can accumulate several outcomes — an
    interview and then a rejection is two rows and one application.
    """
    return await db.scalar(
        select(func.count(distinct(ApplicationOutcome.application_id))).where(condition)
    )


async def application_analytics(db: AsyncSession) -> AnalyticsSummary:
    started = await db.scalar(select(func.count()).select_from(Application))
    submitted = await db.scalar(
        select(func.count()).select_from(Application).where(Application.submitted_at.is_not(None))
    )

    by_state = {
        state.value: count
        for state, count in (
            await db.execute(select(Application.state, func.count()).group_by(Application.state))
        ).all()
    }
    by_outcome = {
        kind.value: count
        for kind, count in (
            await db.execute(
                select(ApplicationOutcome.kind, func.count()).group_by(ApplicationOutcome.kind)
            )
        ).all()
    }

    # Only submitted applications can have drawn a response, so counting the
    # rest in the denominator would dilute every variant's rate with
    # applications nobody ever sent.
    variant_rows = (
        await db.execute(
            select(
                ResumeVariant.id,
                ResumeVariant.role_label,
                func.count(distinct(Application.id)),
                func.count(distinct(case((RESPONDED, Application.id)))),
                func.count(
                    distinct(
                        case((ApplicationOutcome.kind == OutcomeKind.INTERVIEW, Application.id))
                    )
                ),
            )
            .join(
                Application,
                (Application.resume_variant_id == ResumeVariant.id)
                & Application.submitted_at.is_not(None),
            )
            .outerjoin(ApplicationOutcome, ApplicationOutcome.application_id == Application.id)
            .group_by(ResumeVariant.id, ResumeVariant.role_label)
            .order_by(ResumeVariant.role_label)
        )
    ).all()

    return AnalyticsSummary(
        started=started or 0,
        submitted=submitted or 0,
        responded=await _count_applications_with(db, RESPONDED) or 0,
        interviewed=await _count_applications_with(
            db, ApplicationOutcome.kind == OutcomeKind.INTERVIEW
        )
        or 0,
        offers=await _count_applications_with(db, ApplicationOutcome.kind == OutcomeKind.OFFER)
        or 0,
        by_state=by_state,
        by_outcome=by_outcome,
        variants=[
            VariantPerformance(
                variant_id=variant_id,
                role_label=role_label,
                submitted=used,
                responded=responded,
                interviews=interviews,
            )
            for variant_id, role_label, used, responded, interviews in variant_rows
        ],
    )
