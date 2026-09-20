import base64
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.deps import get_db
from app.models.application import Application, ApplicationState
from app.models.draft_answer import DraftAnswer
from app.models.job import Job as JobModel
from app.models.profile import Profile
from app.schemas.application import ApplicationCreate, ApplicationOut, ApplicationTransition
from app.schemas.automation import FillFormResultOut
from app.schemas.draft_answer import DraftAnswerCreate, DraftAnswerOut
from app.services.applications import (
    IllegalStateTransition,
    apply_transition,
    get_or_create_application,
)
from app.services.automation import NoAdapterForUrl, fill_application_form
from app.services.discovery.liveness import Liveness, check_job_liveness
from app.services.tailoring.attach import attach_tailoring_artifacts
from app.services.tailoring.draft_answer import ensure_draft_answer

router = APIRouter()


@router.post("/", response_model=ApplicationOut)
async def create_application(
    payload: ApplicationCreate, db: AsyncSession = Depends(get_db)
) -> Application:
    profile = (
        await db.execute(select(Profile).where(Profile.id == payload.profile_id))
    ).scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Profile {payload.profile_id} not found")

    job = (await db.execute(select(JobModel).where(JobModel.id == payload.job_id))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {payload.job_id} not found")

    return await get_or_create_application(profile, job, db)


@router.get("/", response_model=list[ApplicationOut])
async def list_applications(db: AsyncSession = Depends(get_db)) -> list[Application]:
    result = await db.execute(
        select(Application).order_by(Application.created_at.desc()).limit(50)
    )
    return list(result.scalars().all())


@router.get("/{application_id}", response_model=ApplicationOut)
async def get_application(application_id: int, db: AsyncSession = Depends(get_db)) -> Application:
    return await _get_application_or_404(application_id, db)


async def _get_application_or_404(application_id: int, db: AsyncSession) -> Application:
    application = (
        await db.execute(select(Application).where(Application.id == application_id))
    ).scalar_one_or_none()
    if application is None:
        raise HTTPException(status_code=404, detail=f"Application {application_id} not found")
    return application


async def _load_profile_and_job(
    application: Application, db: AsyncSession
) -> tuple[Profile, JobModel]:
    """The real objects behind an application's FKs, for the services that need
    more than the ids.

    projects must be eager-loaded: profile.full_resume_text reads
    profile.projects, and lazy-loading that outside the greenlet context
    selectinload avoids raises MissingGreenlet rather than quietly working.
    """
    profile = (
        await db.execute(
            select(Profile)
            .options(selectinload(Profile.projects))
            .where(Profile.id == application.profile_id)
        )
    ).scalar_one()
    job = (await db.execute(select(JobModel).where(JobModel.id == application.job_id))).scalar_one()
    return profile, job


async def _guard_job_still_open(application: Application, db: AsyncSession) -> None:
    """Tailoring is the first expensive step — two LLM generations plus a grounding
    verification pass — so it is the right place to confirm the posting still
    exists, rather than finding out at submit time. UNVERIFIABLE is allowed
    through: for aggregator listings there is no honest way to check.
    """
    job = (
        await db.execute(select(JobModel).where(JobModel.id == application.job_id))
    ).scalar_one()

    if await check_job_liveness(job) is not Liveness.CLOSED:
        return

    if job.closed_at is None:
        job.closed_at = datetime.now(UTC)
        await db.commit()

    raise HTTPException(
        status_code=409,
        detail=f"Job {job.id} is no longer accepting applications.",
    )


@router.post("/{application_id}/transition", response_model=ApplicationOut)
async def transition_application(
    application_id: int, payload: ApplicationTransition, db: AsyncSession = Depends(get_db)
) -> Application:
    application = await _get_application_or_404(application_id, db)

    if payload.target_state is ApplicationState.TAILORING:
        await _guard_job_still_open(application, db)
        # Before the state change, not after: an application that says it is
        # tailoring should already have the artifacts it will submit. If
        # generation fails the state is untouched and the move can just be
        # retried, rather than stranding it in tailoring with nothing attached.
        profile, job = await _load_profile_and_job(application, db)
        await attach_tailoring_artifacts(application, profile, job, db)

    try:
        await apply_transition(application, payload.target_state, db)
    except IllegalStateTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return application


@router.post("/{application_id}/draft-answers", response_model=DraftAnswerOut)
async def create_draft_answer(
    application_id: int, payload: DraftAnswerCreate, db: AsyncSession = Depends(get_db)
) -> DraftAnswer:
    application = await _get_application_or_404(application_id, db)
    profile, job = await _load_profile_and_job(application, db)

    return await ensure_draft_answer(application, profile, job, payload.question_text, db)


@router.get("/{application_id}/draft-answers", response_model=list[DraftAnswerOut])
async def list_draft_answers(
    application_id: int, db: AsyncSession = Depends(get_db)
) -> list[DraftAnswer]:
    await _get_application_or_404(application_id, db)
    result = await db.execute(
        select(DraftAnswer)
        .where(DraftAnswer.application_id == application_id)
        .order_by(DraftAnswer.created_at)
    )
    return list(result.scalars().all())


@router.post("/{application_id}/fill-form", response_model=FillFormResultOut)
async def fill_form(application_id: int, db: AsyncSession = Depends(get_db)) -> FillFormResultOut:
    """Drive the real ATS form with a headless browser and return what happened —
    never submits it, per MVP.md's non-negotiable human-approval gate. Safe to
    call from any application state (see fill_application_form's docstring);
    the frontend decides when to offer this action.
    """
    application = await _get_application_or_404(application_id, db)
    profile, job = await _load_profile_and_job(application, db)

    try:
        result = await fill_application_form(application, profile, job, db)
    except NoAdapterForUrl as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    screenshot = result["screenshot"]
    return FillFormResultOut(
        status=result["status"],
        filled_fields=result["filled_fields"],
        skipped_fields=result["skipped_fields"],
        screenshot_base64=base64.b64encode(screenshot).decode("ascii") if screenshot else None,
    )
