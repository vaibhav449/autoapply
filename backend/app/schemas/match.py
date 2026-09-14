from pydantic import BaseModel

from app.schemas.job import JobOut


class JobMatch(BaseModel):
    job: JobOut
    score: float
