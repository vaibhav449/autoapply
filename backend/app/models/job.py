from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# text-embedding-3-small's native output size — see app/services/scoring/embeddings.py
EMBEDDING_DIM = 1536


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_jobs_source_external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str]
    source: Mapped[str]
    title: Mapped[str]
    company: Mapped[str]
    location: Mapped[str | None]
    url: Mapped[str]
    description: Mapped[str | None]
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
