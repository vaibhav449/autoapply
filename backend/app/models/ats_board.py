from datetime import datetime

from sqlalchemy import DateTime, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AtsBoard(Base):
    """A company's job board on an ATS we can read.

    Replaces the hardcoded GREENHOUSE_COMPANIES / LEVER_COMPANIES lists: adding a
    company is now data, not a deploy, and boards can be discovered automatically
    from company names Adzuna surfaces.
    """

    __tablename__ = "ats_boards"
    __table_args__ = (UniqueConstraint("source", "slug", name="uq_ats_boards_source_slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str]
    slug: Mapped[str]
    # The name we went looking for, which is not always what the board calls itself.
    company_name: Mapped[str]
    # The board's own declared name. Fuzzy slug guesses are only trusted once this
    # corroborates them — "New Era India" once matched a board owned by "Sonja Inc."
    verified_name: Mapped[str | None]
    # "seed" | "adzuna" | "user"
    discovered_via: Mapped[str]
    active: Mapped[bool] = mapped_column(default=True, server_default="true")
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
