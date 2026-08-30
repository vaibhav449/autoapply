from fastapi import APIRouter

router = APIRouter()


@router.get("/funnel")
async def funnel() -> dict:
    return {}
