from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_db
from app.models.job import Job as JobModel
from app.schemas.job import Job, JobOut
from app.services.discovery import save_jobs
from app.services.discovery.adzuna import discover_adzuna_jobs
from app.services.discovery.greenhouse import discover_greenhouse_jobs
from app.services.discovery.jooble import discover_jooble_jobs
from app.services.discovery.json_ld import fetch_json_ld_jobs
from app.services.discovery.lever import discover_lever_jobs
from app.services.discovery.llm_extraction import fetch_llm_extracted_jobs
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


@router.get("/discover/adzuna", response_model=list[Job])
async def discover_jobs_adzuna(
    query: str, location: str = "", country: str = "in", db: AsyncSession = Depends(get_db)
) -> list[Job]:
    return await discover_adzuna_jobs(query, location, country, db)


@router.get("/discover/jooble", response_model=list[Job])
async def discover_jobs_jooble(
    query: str, location: str = "", db: AsyncSession = Depends(get_db)
) -> list[Job]:
    return await discover_jooble_jobs(query, location, db)


@router.get("/discover/url", response_model=list[Job])
async def discover_jobs_from_url(url: str, db: AsyncSession = Depends(get_db)) -> list[Job]:
    resolved = resolve_known_ats(url)
    if resolved is not None:
        source, company_slug = resolved
        return await DISCOVER_FUNCS[source](company_slug, db)

    jobs = await fetch_json_ld_jobs(url)
    if jobs:
        await save_jobs(jobs, db)
        return jobs

    jobs = await fetch_llm_extracted_jobs(url)
    if jobs:
        await save_jobs(jobs, db)
        return jobs

    raise HTTPException(
        status_code=422,
        detail="Couldn't find any job postings on this page through any strategy.",
    )
