from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_applications() -> list[dict]:
    return []
