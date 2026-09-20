import enum
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, str_enum_column
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

    # Things a resume structurally cannot answer, which real application forms
    # ask on nearly every posting. Without them the automation had no honest
    # option but to skip the field or write "my resume does not specify" into
    # it — every one of these was observed being asked on a live Greenhouse
    # form. Free text rather than numbers or enums because forms ask in wildly
    # different units and phrasings (LPA, annual, monthly), and the answer is
    # rendered by an LLM into whatever shape the form wants.
    notice_period: Mapped[str | None] = mapped_column(default=None)
    current_ctc: Mapped[str | None] = mapped_column(default=None)
    expected_ctc: Mapped[str | None] = mapped_column(default=None)
    preferred_locations: Mapped[str | None] = mapped_column(default=None)
    work_authorization: Mapped[str | None] = mapped_column(default=None)
    linkedin_url: Mapped[str | None] = mapped_column(default=None)
    portfolio_url: Mapped[str | None] = mapped_column(default=None)
    # Tri-state on purpose: None means "not told us", which is different from a
    # definite No and must not be answered as one.
    has_offer_in_hand: Mapped[bool | None] = mapped_column(default=None)
    target_level: Mapped[TargetLevel] = str_enum_column(
        TargetLevel, "target_level", default=TargetLevel.MID
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
