import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


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
    state: Mapped[ApplicationState] = mapped_column(
        # values_callable: without it, SQLAlchemy stores the enum's uppercase member
        # NAME ("INTERESTED") in Postgres, not the lowercase .value ("interested")
        # everything else (the API, this class itself) actually treats as the value.
        SAEnum(
            ApplicationState,
            name="application_state",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=ApplicationState.INTERESTED,
    )
    cover_letter_id: Mapped[int | None] = mapped_column(ForeignKey("cover_letters.id"))
    resume_variant_id: Mapped[int | None] = mapped_column(ForeignKey("resume_variants.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
