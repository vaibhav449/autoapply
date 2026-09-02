from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str]
    source: Mapped[str]
    title: Mapped[str]
    company: Mapped[str]
    location: Mapped[str | None]
    url: Mapped[str]
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
