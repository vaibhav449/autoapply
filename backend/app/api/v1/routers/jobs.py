from fastapi import APIRouter

from app.schemas.job import Job
from app.services.discovery.greenhouse import fetch_greenhouse_jobs

router = APIRouter()


@router.get("/")
async def list_jobs() -> list[dict]:
    return []


@router.get("/discover", response_model=list[Job])
async def discover_jobs(company: str) -> list[Job]:
    return await fetch_greenhouse_jobs(company)
