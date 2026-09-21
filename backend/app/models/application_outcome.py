import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, str_enum_column


class OutcomeKind(str, enum.Enum):
    """What came back after an application went out.

    NO_RESPONSE is recorded deliberately rather than inferred from silence —
    "heard nothing and I am closing this out" is a decision with a date on it,
    and the funnel needs it separated from applications still in flight.
    """

    NO_RESPONSE = "no_response"
    REJECTED = "rejected"
    INTERVIEW = "interview"
    OFFER = "offer"


class ApplicationOutcome(Base):
    """One thing that happened to an application after it was submitted.

    A log rather than a state, which settles automation-plan.md §9: MVP.md asks
    for a funnel of applied -> response -> interview, and an application that
    reached an interview and was then rejected has to count in both. A single
    current-state column can only remember the last thing that happened, so it
    would quietly undercount every stage an application passed through.

    Application.state stays what it is — where something sits in the user's own
    workflow — while these record what the company did, which is not the same
    question and does not move in lockstep.
    """

    __tablename__ = "application_outcomes"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"))
    kind: Mapped[OutcomeKind] = str_enum_column(OutcomeKind, "outcome_kind")
    # When it actually happened, which is not when it was typed in — a rejection
    # email sat unread for three days still belongs to the day it arrived.
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
