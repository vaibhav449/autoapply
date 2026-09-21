from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DraftAnswer(Base):
    """One generated answer to one custom application question, scoped to a
    specific Application rather than (profile, job) directly — since Application
    already carries a unique (profile_id, job_id) pair, application_id alone fully
    identifies which candidate and which posting this answer is grounded against.

    unverified_claims mirrors ResumeVariant: an empty list means the grounding
    check ran and found nothing to flag, not "not yet checked".
    """

    __tablename__ = "draft_answers"
    __table_args__ = (
        UniqueConstraint("application_id", "question_text", name="uq_draft_answers_application_question"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"))
    question_text: Mapped[str]
    answer_text: Mapped[str]
    unverified_claims: Mapped[list[str]] = mapped_column(JSONB, default=list)
    # What this answer was generated from — the prompt version plus the resume
    # and description it was grounded in — so improving the prompt or editing
    # the resume regenerates it instead of serving the old text forever.
    #
    # NULL means nobody generated it: a person wrote this, and it is not ours to
    # overwrite no matter how far the prompt has moved on.
    fingerprint: Mapped[str | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
