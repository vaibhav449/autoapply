from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.job import EMBEDDING_DIM


class Profile(Base):
    """A candidate's data to score jobs against — not a user/auth account.

    Linking this to real authentication is future work; for now it only exists
    to give scoring something concrete to embed and compare jobs to.
    """

    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    resume_text: Mapped[str]
    years_experience: Mapped[float]
    preferences: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)

    projects: Mapped[list["ProfileProject"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )


class ProfileProject(Base):
    """One project's in-depth markdown write-up, belonging to a single profile."""

    __tablename__ = "profile_projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"))
    title: Mapped[str]
    content_md: Mapped[str]

    profile: Mapped["Profile"] = relationship(back_populates="projects")
