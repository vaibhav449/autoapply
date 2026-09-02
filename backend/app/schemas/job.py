from pydantic import BaseModel, HttpUrl


class Job(BaseModel):
    external_id: str
    source: str
    title: str
    company: str
    location: str | None = None
    url: HttpUrl
