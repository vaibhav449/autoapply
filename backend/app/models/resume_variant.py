from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, LargeBinary, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ResumeVariant(Base):
    """A resume tailored for a role category, not a single job — generated once
    per (profile, role_label), grounded in the candidate's real content plus a
    real cluster of market JDs for that role (context only, never attributed to
    the candidate). unverified_claims holds the verification pass's findings —
    an empty list means nothing was flagged, not "not yet checked".
    """

    __tablename__ = "resume_variants"
    __table_args__ = (
        UniqueConstraint("profile_id", "role_label", name="uq_resume_variants_profile_role"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"))
    role_label: Mapped[str]
    emphasis_note: Mapped[str | None]
    generated_content: Mapped[str]
    unverified_claims: Mapped[list[str]] = mapped_column(JSONB, default=list)
    # Rendered lazily on first request, then cached here. Tens of KB per row, so
    # BYTEA rather than object storage - no extra infrastructure for v1, and the
    # bytes stay transactional with the content they were rendered from.
    pdf_bytes: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
