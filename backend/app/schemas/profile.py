from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.profile import TargetLevel


class ProfileProjectCreate(BaseModel):
    title: str
    content_md: str


class CandidateApplicationFields(BaseModel):
    """The answers a resume structurally cannot supply, asked on nearly every
    real application form. Optional everywhere: an unanswered field stays
    unanswered on the form too, rather than being guessed.
    """

    notice_period: str | None = None
    current_ctc: str | None = None
    expected_ctc: str | None = None
    preferred_locations: str | None = None
    work_authorization: str | None = None
    linkedin_url: str | None = None
    portfolio_url: str | None = None
    has_offer_in_hand: bool | None = None


class ProfileCreate(CandidateApplicationFields):
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


class ProfileUpdate(CandidateApplicationFields):
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


class ProfileOut(CandidateApplicationFields):
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
