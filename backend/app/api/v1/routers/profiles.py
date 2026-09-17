from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.deps import get_db
from app.models.cover_letter import CoverLetter
from app.models.job import Job as JobModel
from app.models.profile import Profile, ProfileProject
from app.models.resume_variant import ResumeVariant
from app.schemas.cover_letter import CoverLetterOut
from app.schemas.match import JobMatch
from app.schemas.profile import ProfileCreate, ProfileOut, ProfileUpdate
from app.schemas.resume_variant import ResumeVariantCreate, ResumeVariantOut
from app.services.scoring.embeddings import embed_profile
from app.services.scoring.score import rank_jobs_for_profile
from app.services.tailoring.cover_letter import ensure_cover_letter
from app.services.tailoring.resume_pdf import (
    UnrenderableResumeContent,
    ensure_resume_pdf,
    resume_pdf_filename,
)
from app.services.tailoring.resume_variant import create_resume_variant

router = APIRouter()


async def _get_profile_or_404(profile_id: int, db: AsyncSession) -> Profile:
    result = await db.execute(
        select(Profile).options(selectinload(Profile.projects)).where(Profile.id == profile_id)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")
    return profile


@router.post("/", response_model=ProfileOut)
async def create_profile(payload: ProfileCreate, db: AsyncSession = Depends(get_db)) -> Profile:
    profile = Profile(
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        location=payload.location,
        resume_text=payload.resume_text,
        years_experience=payload.years_experience,
        target_level=payload.target_level,
        preferences=payload.preferences,
        projects=[ProfileProject(title=p.title, content_md=p.content_md) for p in payload.projects],
    )
    db.add(profile)
    await db.commit()

    await embed_profile(profile, db)

    return profile


@router.get("/", response_model=list[ProfileOut])
async def list_profiles(db: AsyncSession = Depends(get_db)) -> list[Profile]:
    result = await db.execute(
        select(Profile)
        .options(selectinload(Profile.projects))
        .order_by(Profile.created_at.desc())
        .limit(50)
    )
    return list(result.scalars().all())


@router.get("/{profile_id}", response_model=ProfileOut)
async def get_profile(profile_id: int, db: AsyncSession = Depends(get_db)) -> Profile:
    return await _get_profile_or_404(profile_id, db)


@router.patch("/{profile_id}", response_model=ProfileOut)
async def update_profile(
    profile_id: int, payload: ProfileUpdate, db: AsyncSession = Depends(get_db)
) -> Profile:
    profile = await _get_profile_or_404(profile_id, db)

    updates = payload.model_dump(exclude_unset=True)
    resume_changed = "resume_text" in updates and updates["resume_text"] != profile.resume_text
    for field, value in updates.items():
        setattr(profile, field, value)
    await db.commit()

    # full_resume_text (and therefore the embedding matches are ranked against)
    # only depends on resume_text and projects, and projects aren't editable here.
    if resume_changed:
        await embed_profile(profile, db)

    return profile


@router.get("/{profile_id}/matches", response_model=list[JobMatch])
async def get_profile_matches(profile_id: int, db: AsyncSession = Depends(get_db)) -> list[JobMatch]:
    profile = await _get_profile_or_404(profile_id, db)
    if profile.embedding is None:
        raise HTTPException(status_code=422, detail="Profile has no embedding yet.")

    ranked = await rank_jobs_for_profile(profile, db)
    return [
        JobMatch(
            job=result.job,
            score=result.score,
            tier=result.tier.name.lower(),
            experience=result.experience.value,
            note=result.note,
            stale=result.stale,
        )
        for result in ranked
    ]


@router.get("/{profile_id}/jobs/{job_id}/cover-letter", response_model=CoverLetterOut)
async def get_cover_letter(
    profile_id: int, job_id: int, db: AsyncSession = Depends(get_db)
) -> CoverLetter:
    profile = await _get_profile_or_404(profile_id, db)

    result = await db.execute(select(JobModel).where(JobModel.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return await ensure_cover_letter(profile, job, db)


@router.post("/{profile_id}/resume-variants", response_model=ResumeVariantOut)
async def create_resume_variant_route(
    profile_id: int, payload: ResumeVariantCreate, db: AsyncSession = Depends(get_db)
) -> ResumeVariant:
    profile = await _get_profile_or_404(profile_id, db)
    try:
        return await create_resume_variant(profile, payload.role_label, payload.emphasis_note, db)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"A resume variant for '{payload.role_label}' already exists for this profile.",
        ) from None


@router.get("/{profile_id}/resume-variants", response_model=list[ResumeVariantOut])
async def list_resume_variants(
    profile_id: int, db: AsyncSession = Depends(get_db)
) -> list[ResumeVariant]:
    await _get_profile_or_404(profile_id, db)
    result = await db.execute(
        select(ResumeVariant)
        .where(ResumeVariant.profile_id == profile_id)
        .order_by(ResumeVariant.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{profile_id}/resume-variants/{variant_id}/pdf")
async def get_resume_variant_pdf(
    profile_id: int, variant_id: int, db: AsyncSession = Depends(get_db)
) -> Response:
    profile = await _get_profile_or_404(profile_id, db)

    # Scoped to this profile, so another profile's variant can't be read by id.
    result = await db.execute(
        select(ResumeVariant).where(
            ResumeVariant.id == variant_id, ResumeVariant.profile_id == profile_id
        )
    )
    variant = result.scalar_one_or_none()
    if variant is None:
        raise HTTPException(
            status_code=404, detail=f"Resume variant {variant_id} not found for this profile"
        )

    try:
        pdf_bytes = await ensure_resume_pdf(profile, variant, db)
    except UnrenderableResumeContent as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Resume content cannot be rendered with the built-in fonts: {exc}",
        ) from exc

    filename = resume_pdf_filename(profile, variant)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
