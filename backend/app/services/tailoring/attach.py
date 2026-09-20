import math

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.job import Job as JobModel
from app.models.profile import Profile
from app.models.resume_variant import ResumeVariant
from app.services.scoring.embeddings import embed_text
from app.services.tailoring.cover_letter import ensure_cover_letter

# Below this, the closest variant is treated as "none of these fit" and the
# application keeps the untailored base resume. A variant emphasizes the
# candidate's real content for one kind of role, so sending a frontend-shaped
# resume to a data science posting is worse than sending the plain one.
#
# Measured against real embeddings of real role labels and job titles rather
# than picked by feel — a first guess of 0.45 would have matched "Machine
# Learning Engineer" to a Frontend Engineer posting:
#
#   0.888  ML Engineer          -> Machine Learning Engineer II   (want match)
#   0.616  ML Engineer          -> ML Engineer (Full Stack)       (want match)
#   0.591  Full Stack Developer -> Software Engineer - Web        (want match)
#   ----------------------------------------------------------- 0.56
#   0.534  ML Engineer          -> Frontend Engineer              (want no match)
#   0.386  Backend Engineer     -> Data Scientist                 (want no match)
#   0.294  Backend Engineer     -> Registered Nurse               (want no match)
#
# The usable gap is only ~0.06, so job-title similarity is a weak signal and
# borderline cases land on the safe side: no variant, base resume, nothing
# silently mis-emphasized.
MIN_ROLE_SIMILARITY = 0.56


def cosine_similarity(a: list[float], b: list[float]) -> float:
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    if not norm:
        return 0.0
    return sum(x * y for x, y in zip(a, b, strict=True)) / norm


async def select_resume_variant(
    profile: Profile, job: JobModel, db: AsyncSession
) -> ResumeVariant | None:
    """The role variant closest to this job, or None to keep the base resume.

    Compared against the job TITLE rather than job.embedding: that vector is
    built from the whole posting (title plus description), while a role_label is
    a short phrase. Matching phrase against phrase is the like-for-like
    comparison; matching a phrase against a full posting mostly measures length.
    """
    variants = list(
        (
            await db.execute(select(ResumeVariant).where(ResumeVariant.profile_id == profile.id))
        )
        .scalars()
        .all()
    )
    if not variants:
        return None

    job_vector = await embed_text(job.title)
    best: tuple[float, ResumeVariant] | None = None
    for variant in variants:
        score = cosine_similarity(job_vector, await embed_text(variant.role_label))
        if best is None or score > best[0]:
            best = (score, variant)

    assert best is not None
    return best[1] if best[0] >= MIN_ROLE_SIMILARITY else None


async def attach_tailoring_artifacts(
    application: Application, profile: Profile, job: JobModel, db: AsyncSession
) -> None:
    """Link the artifacts this application will actually submit.

    Until this ran, both FKs were dead columns — a candidate could generate
    resume variants and cover letters and none of them ever reached the form,
    which filled from the untailored base resume every time.

    An already-chosen variant is never overwritten: once a human has picked one
    for this application, re-entering tailoring must not silently swap it.
    """
    cover_letter = await ensure_cover_letter(profile, job, db)
    application.cover_letter_id = cover_letter.id

    if application.resume_variant_id is None:
        variant = await select_resume_variant(profile, job, db)
        if variant is not None:
            application.resume_variant_id = variant.id

    await db.commit()
