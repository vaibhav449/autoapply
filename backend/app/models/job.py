from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
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
    # Stamped on every sighting, including re-sightings. Without it a poll that
    # re-sees a job teaches us nothing and closed postings never leave the pool.
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Consecutive complete board sweeps this job was absent from. Requiring more
    # than one absorbs a single flaky fetch before anything is declared dead.
    missed_sweeps: Mapped[int] = mapped_column(default=0, server_default="0")
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    # Cached JobRequirements.model_dump() — None means "not extracted yet", not "no requirements".
    requirements: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Fingerprint of the description `requirements` was extracted from. Descriptions
    # get backfilled after a job is first seen, so a cache keyed on row identity
    # alone keeps serving the pre-backfill answer forever.
    requirements_fingerprint: Mapped[str | None] = mapped_column(nullable=True)
