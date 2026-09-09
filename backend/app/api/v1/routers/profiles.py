from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.deps import get_db
from app.models.profile import Profile, ProfileProject
from app.schemas.profile import ProfileCreate, ProfileOut
from app.services.scoring.embeddings import embed_profile

router = APIRouter()


@router.post("/", response_model=ProfileOut)
async def create_profile(payload: ProfileCreate, db: AsyncSession = Depends(get_db)) -> Profile:
    profile = Profile(
        name=payload.name,
        resume_text=payload.resume_text,
        years_experience=payload.years_experience,
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
    result = await db.execute(
        select(Profile).options(selectinload(Profile.projects)).where(Profile.id == profile_id)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")
    return profile
