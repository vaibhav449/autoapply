from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CoverLetter(Base):
    """A generated pitch for one (profile, job) pair — cached, never regenerated
    once it exists. Grounded strictly in that profile's real content plus that
    one job's real description; nothing else enters the prompt.
    """

    __tablename__ = "cover_letters"
    __table_args__ = (UniqueConstraint("profile_id", "job_id", name="uq_cover_letters_profile_job"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"))
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    content: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
