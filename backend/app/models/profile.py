import enum
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.job import EMBEDDING_DIM


class TargetLevel(str, enum.Enum):
    """What the candidate is actually shopping for.

    Distinct from years_experience, which says what they have. A final-year
    student with substantial projects reads "senior" to a similarity search
    while needing internships — without this, discovery collects a pool the
    candidate cannot apply to and ranking can only sort what it was given.
    """

    INTERN = "intern"
    NEW_GRAD = "new_grad"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"


class Profile(Base):
    """A candidate's data to score jobs against — not a user/auth account.

    Linking this to real authentication is future work; for now it only exists
    to give scoring something concrete to embed and compare jobs to.
    """

    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    email: Mapped[str]
    phone: Mapped[str | None]
    location: Mapped[str | None]
    resume_text: Mapped[str]
    years_experience: Mapped[float]
    target_level: Mapped[TargetLevel] = mapped_column(
        SAEnum(
            TargetLevel,
            name="target_level",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=TargetLevel.MID,
    )
    preferences: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)

    projects: Mapped[list["ProfileProject"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )

    @property
    def full_resume_text(self) -> str:
        """Resume plus every project write-up, concatenated — the one grounding
        source every LLM-facing feature (embeddings, cover letters, resume
        variants) reads from, so they all see the exact same real content.
        """
        project_text = "\n\n".join(f"## {p.title}\n{p.content_md}" for p in self.projects)
        return self.resume_text if not project_text else f"{self.resume_text}\n\n{project_text}"


class ProfileProject(Base):
    """One project's in-depth markdown write-up, belonging to a single profile."""

    __tablename__ = "profile_projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"))
    title: Mapped[str]
    content_md: Mapped[str]

    profile: Mapped["Profile"] = relationship(back_populates="projects")
