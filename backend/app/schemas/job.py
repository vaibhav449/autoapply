from datetime import datetime

from pydantic import BaseModel, ConfigDict, HttpUrl


class Job(BaseModel):
    external_id: str
    source: str
    title: str
    company: str
    location: str | None = None
    url: HttpUrl


class JobOut(Job):
    model_config = ConfigDict(from_attributes=True)

    id: int
    discovered_at: datetime
