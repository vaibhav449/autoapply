from sqlalchemy import case, distinct, func, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.application_outcome import ApplicationOutcome, OutcomeKind
from app.models.fill_attempt import FillAttempt
from app.models.resume_variant import ResumeVariant
from app.schemas.analytics import AnalyticsSummary, SkippedField, VariantPerformance

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


# How many fields to rank. The point is a shortlist to act on, not a census of
# every question any form has ever asked.
SKIPPED_FIELD_LIMIT = 20


async def _skipped_fields(db: AsyncSession) -> list[SkippedField]:
    """Rank what the filler has had to leave for a human.

    The skip list is a JSONB array per attempt, so it is expanded into rows in
    Postgres (jsonb_array_elements_text) rather than pulled into Python and
    counted there — the aggregate is the whole point, and the rows themselves
    are of no use here.
    """
    # Spelled as an explicit LATERAL ... ON true rather than letting the
    # function sit loose in the FROM list: Postgres accepts both, but only this
    # form has a join condition SQLAlchemy can see, and without one it warns
    # about a cartesian product on every call — which is exactly how a real one
    # would later go unnoticed.
    # render_derived() is what emits AS alias(field) — without it the derived
    # table has no column of that name and Postgres rejects the query outright.
    skipped = (
        func.jsonb_array_elements_text(FillAttempt.skipped_fields)
        .table_valued("field")
        .render_derived()
        .lateral()
    )
    rows = (
        await db.execute(
            select(
                skipped.c.field,
                func.count(),
                func.count(distinct(FillAttempt.application_id)),
            )
            .select_from(FillAttempt)
            .join(skipped, true())
            .group_by(skipped.c.field)
            # Distinct applications first: a form filled three times over is one
            # problem, not three, and ranking by raw count would say otherwise.
            .order_by(func.count(distinct(FillAttempt.application_id)).desc(), func.count().desc())
            .limit(SKIPPED_FIELD_LIMIT)
        )
    ).all()
    return [
        SkippedField(field=name, runs=runs, applications=applications)
        for name, runs, applications in rows
    ]


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
        fill_runs=await db.scalar(select(func.count()).select_from(FillAttempt)) or 0,
        skipped_fields=await _skipped_fields(db),
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
