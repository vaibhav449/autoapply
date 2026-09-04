from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_db
from app.models.job import Job as JobModel
from app.schemas.job import Job, JobOut
from app.services.discovery.greenhouse import discover_greenhouse_jobs
from app.services.discovery.lever import discover_lever_jobs
from app.services.discovery.url_resolver import resolve_known_ats

router = APIRouter()

DISCOVER_FUNCS = {
    "greenhouse": discover_greenhouse_jobs,
    "lever": discover_lever_jobs,
}


@router.get("/", response_model=list[JobOut])
async def list_jobs(db: AsyncSession = Depends(get_db)) -> list[JobModel]:
    result = await db.execute(select(JobModel).order_by(JobModel.discovered_at.desc()).limit(50))
    return list(result.scalars().all())


@router.get("/discover/greenhouse", response_model=list[Job])
async def discover_jobs_greenhouse(company: str, db: AsyncSession = Depends(get_db)) -> list[Job]:
    return await discover_greenhouse_jobs(company, db)


@router.get("/discover/lever", response_model=list[Job])
async def discover_jobs_lever(company: str, db: AsyncSession = Depends(get_db)) -> list[Job]:
    return await discover_lever_jobs(company, db)


@router.get("/discover/url", response_model=list[Job])
async def discover_jobs_from_url(url: str, db: AsyncSession = Depends(get_db)) -> list[Job]:
    resolved = resolve_known_ats(url)
    if resolved is None:
        raise HTTPException(
            status_code=422,
            detail="Not a recognized ATS URL yet — JSON-LD and LLM-extraction fallbacks aren't built.",
        )

    source, company_slug = resolved
    return await DISCOVER_FUNCS[source](company_slug, db)
