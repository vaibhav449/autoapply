from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProfileProjectCreate(BaseModel):
    title: str
    content_md: str


class ProfileCreate(BaseModel):
    name: str
    resume_text: str
    years_experience: float
    preferences: dict = {}
    projects: list[ProfileProjectCreate] = []


class ProfileProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    content_md: str


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    resume_text: str
    years_experience: float
    preferences: dict
    created_at: datetime
    projects: list[ProfileProjectOut] = []
