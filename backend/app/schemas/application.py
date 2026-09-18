from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.application import ApplicationState


class ApplicationCreate(BaseModel):
    profile_id: int
    job_id: int


class ApplicationTransition(BaseModel):
    target_state: ApplicationState


class ApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    profile_id: int
    job_id: int
    state: ApplicationState
    cover_letter_id: int | None
    resume_variant_id: int | None
    created_at: datetime
    submitted_at: datetime | None
    # Read off Application.legal_next_states (a property, not a column) via
    # from_attributes — the one real edge list, not a frontend-side copy of it.
    legal_next_states: list[ApplicationState]
