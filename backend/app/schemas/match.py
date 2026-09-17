from pydantic import BaseModel

from app.schemas.job import JobOut


class JobMatch(BaseModel):
    job: JobOut
    score: float
    # "qualified" | "stretch" | "unverified" — results are already sorted by this,
    # so the client renders in order and uses the label purely for display.
    tier: str
    experience: str
    note: str | None = None
    stale: bool = False
