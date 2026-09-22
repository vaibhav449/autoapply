from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_db
from app.schemas.analytics import AnalyticsSummary
from app.services.analytics import application_analytics

router = APIRouter()


@router.get("/", response_model=AnalyticsSummary)
async def summary(db: AsyncSession = Depends(get_db)) -> AnalyticsSummary:
    """Counts of what actually happened, computed live.

    Deliberately absent: "time saved" and LLM cost, both of which MVP.md lists.
    Neither is recorded anywhere — fill results are returned to the caller and
    never persisted, and no token spend is tracked — so any number here would
    be an invented constant dressed up as a measurement. They belong here once
    something real is being recorded to compute them from.
    """
    return await application_analytics(db)
