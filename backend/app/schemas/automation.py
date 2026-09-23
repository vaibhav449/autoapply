from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.fill_attempt import FillAttemptStatus


class FillAttemptOut(BaseModel):
    """One recorded run of the form-filler.

    The screenshot itself is deliberately not a field here: it is a full-page
    PNG, and an application accumulates a history of attempts. Base64-ing
    several of those into one JSON response would cost megabytes to show a list
    of dates. Callers fetch it from .../fill-attempts/{id}/screenshot instead,
    the same way a resume PDF is linked rather than inlined.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    status: FillAttemptStatus
    filled_fields: dict[str, str]
    skipped_fields: list[str]
    duration_ms: int
    created_at: datetime
    # Whether that endpoint has anything to serve — a run that never found the
    # form has no screenshot, so the reviewer gets told so instead of a broken
    # image. Computed in SQL (see fill_attempt_rows) precisely so that asking
    # this question does not drag every PNG out of the database.
    has_screenshot: bool
