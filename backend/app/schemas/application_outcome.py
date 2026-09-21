from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.application_outcome import OutcomeKind


class ApplicationOutcomeCreate(BaseModel):
    kind: OutcomeKind
    note: str | None = None
    # Optional so the common case ("this just happened") needs no date, while a
    # rejection found in a week-old inbox can still be filed under the day it
    # arrived rather than the day it was noticed.
    occurred_at: datetime | None = None


class ApplicationOutcomeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    kind: OutcomeKind
    note: str | None
    occurred_at: datetime
    created_at: datetime
