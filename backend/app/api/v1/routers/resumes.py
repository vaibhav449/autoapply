from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_resumes() -> list[dict]:
    return []
