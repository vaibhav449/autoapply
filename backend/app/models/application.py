import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, str_enum_column


class ApplicationState(str, enum.Enum):
    """Mirrors MVP.md's state diagram, starting from "interested" rather than
    "discovered"/"scored" — see automation-plan.md §3 for why those two don't
    exist as persisted states in this system.
    """

    INTERESTED = "interested"
    TAILORING = "tailoring"
    READY_FOR_REVIEW = "ready_for_review"
    PENDING_CAPTCHA = "pending_captcha"
    APPROVED = "approved"
    REJECTED_BY_USER = "rejected_by_user"
    SUBMITTED = "submitted"
    RESPONSE_TRACKED = "response_tracked"


# Lives beside ApplicationState, not in the services layer, so Application.
# legal_next_states below can read it without a model -> service import (which
# would be backwards - services/applications already imports FROM this module).
# services/applications/__init__.py imports this same dict rather than keeping
# its own copy, so there is exactly one edge list for the whole state machine.
ALLOWED_TRANSITIONS: dict[ApplicationState, set[ApplicationState]] = {
    ApplicationState.INTERESTED: {ApplicationState.TAILORING, ApplicationState.REJECTED_BY_USER},
    ApplicationState.TAILORING: {
        ApplicationState.READY_FOR_REVIEW,
        ApplicationState.REJECTED_BY_USER,
    },
    ApplicationState.READY_FOR_REVIEW: {
        ApplicationState.APPROVED,
        ApplicationState.PENDING_CAPTCHA,
        ApplicationState.REJECTED_BY_USER,
    },
    ApplicationState.PENDING_CAPTCHA: {
        ApplicationState.SUBMITTED,
        ApplicationState.REJECTED_BY_USER,
    },
    ApplicationState.APPROVED: {ApplicationState.SUBMITTED, ApplicationState.REJECTED_BY_USER},
    ApplicationState.SUBMITTED: {ApplicationState.RESPONSE_TRACKED},
    ApplicationState.RESPONSE_TRACKED: set(),
    ApplicationState.REJECTED_BY_USER: set(),
}


class Application(Base):
    """Created only when a user shows real intent (clicks "apply" on a match) —
    not one row per scored job. profile_id/job_id are already both known-valid
    by that point via the existing discovery+scoring pipeline.
    """

    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("profile_id", "job_id", name="uq_applications_profile_job"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"))
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    state: Mapped[ApplicationState] = str_enum_column(
        ApplicationState, "application_state", default=ApplicationState.INTERESTED
    )
    cover_letter_id: Mapped[int | None] = mapped_column(ForeignKey("cover_letters.id"))
    resume_variant_id: Mapped[int | None] = mapped_column(ForeignKey("resume_variants.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def legal_next_states(self) -> list[ApplicationState]:
        """Read by ApplicationOut (from_attributes=True) so the frontend's
        transition buttons come from the one real edge list instead of a
        hand-copied duplicate that could silently drift from it.
        """
        return sorted(ALLOWED_TRANSITIONS[self.state], key=lambda state: state.value)
