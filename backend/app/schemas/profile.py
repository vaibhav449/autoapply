from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.profile import TargetLevel


class ProfileProjectCreate(BaseModel):
    title: str
    content_md: str


class ProfileCreate(BaseModel):
    name: str
    email: EmailStr
    phone: str | None = None
    location: str | None = None
    resume_text: str
    years_experience: float
    # What they want next, which is not implied by what they have — a final-year
    # student with heavyweight projects still needs internships.
    target_level: TargetLevel = TargetLevel.MID
    preferences: dict = {}
    projects: list[ProfileProjectCreate] = []


class ProfileUpdate(BaseModel):
    """All fields optional by design: a PATCH payload changes only what it
    includes. The route reads this via model_dump(exclude_unset=True) so an
    omitted field is left alone rather than reset to None.

    Deliberately excludes `projects` — add/remove/reorder semantics for a list
    are a different feature, and this screen exists to fix target_level being
    stuck at profile creation, not to become a full profile editor.
    """

    name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    location: str | None = None
    resume_text: str | None = None
    years_experience: float | None = None
    target_level: TargetLevel | None = None
    preferences: dict | None = None


class ProfileProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    content_md: str


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    phone: str | None
    location: str | None
    resume_text: str
    years_experience: float
    target_level: str
    preferences: dict
    created_at: datetime
    projects: list[ProfileProjectOut] = []
