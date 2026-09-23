import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, LargeBinary, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, str_enum_column


class FillAttemptStatus(str, enum.Enum):
    """How a run against the real form ended.

    Mirrors automation.base.FillStatus, which is a Literal rather than this enum
    on purpose: the adapter layer drives a browser and knows nothing about the
    database, and giving it a model import to get a status name would be the
    wrong direction entirely. test_fill_attempt_status_matches_fill_status keeps
    the two from drifting apart.
    """

    FILLED = "filled"
    CAPTCHA_REQUIRED = "captcha_required"
    FORM_NOT_FOUND = "form_not_found"


class FillAttempt(Base):
    """One run of the form-filler against a live posting.

    Append-only, for the same reason ApplicationOutcome is: a fill retried after
    a human clears a CAPTCHA is a second attempt, and the difference between the
    two is the informative part — which fields held the second time, which were
    skipped both times. Keeping only the latest would erase exactly that.

    Before this table the whole result lived in React state, so the review it
    exists to support — "check what I skipped before you submit by hand" — was
    gone the moment the reviewer left for the posting and came back.
    """

    __tablename__ = "fill_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), index=True)
    status: Mapped[FillAttemptStatus] = str_enum_column(FillAttemptStatus, "fill_attempt_status")
    # field identifier -> what was written. Keys are whatever the adapter used to
    # name the field: a CSS selector for a core field, the question's own text for
    # a custom one. Stored as-is rather than normalised, because the point of
    # reading this back is to recognise the field on the real form.
    filled_fields: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    skipped_fields: Mapped[list[str]] = mapped_column(JSONB, default=list)
    # Full-page PNG of the filled form. Hundreds of KB per row, so BYTEA rather
    # than object storage — same trade ResumeVariant.pdf_bytes already makes, and
    # a handful of attempts per application keeps it bounded.
    screenshot: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    # How long the run took. Recorded because it is the one cost of a fill that
    # is measured rather than estimated; it is NOT a time-saved figure, which
    # would need a manual baseline nobody has measured (see the analytics page).
    duration_ms: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
